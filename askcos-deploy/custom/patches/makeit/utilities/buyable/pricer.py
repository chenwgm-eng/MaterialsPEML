import gzip
import json
import os
import threading
import time
import makeit.global_config as gc
import rdkit.Chem as Chem
from collections import defaultdict
from tqdm import tqdm
from makeit.utilities.io.logger import MyLogger
import makeit.utilities.io.pickle as pickle
from pymongo import MongoClient, errors
from multiprocessing import Manager
# 单一事实来源：EXCLUDE_SMILES 与 SMILES 规范化（与 sync_buyables 共用）
from makeit.utilities.buyable.buyables_exclusions import (
    EXCLUDE_SMILES, canonical_smiles, enterprise_refresh_due,
)
pricer_loc = 'pricer'


class Pricer:
    '''
    The Pricer class is used to look up the ppg of chemicals if they
    are buyable.

    Buyable sources (checked in order, first hit wins):
      1. Enterprise material library (industrialization.raw_materials in
         PostgreSQL). Queried live with a TTL cache so newly added materials
         are picked up without a process restart.
      2. ASKCOS standard buyables flat file.
    '''

    # PostgreSQL connection for the enterprise material library. The password
    # MUST be injected via ENTERPRISE_DB_PASSWORD at deploy time; it is never
    # hard-coded here. If the required env vars are missing, the enterprise
    # source is disabled (with a clear log) and the ASKCOS flat file remains.
    ENTERPRISE_DB = {
        'host': os.environ.get('ENTERPRISE_DB_HOST', '172.18.0.1'),
        'port': int(os.environ.get('ENTERPRISE_DB_PORT', '5433')),
        'dbname': os.environ.get('ENTERPRISE_DB_NAME', 'batteryemcl'),
        'user': os.environ.get('ENTERPRISE_DB_USER', 'batteryemcl'),
        'password': os.environ.get('ENTERPRISE_DB_PASSWORD'),  # no default
        'table': os.environ.get('ENTERPRISE_DB_TABLE', 'industrialization.raw_materials'),
    }
    # Enterprise materials are treated as buyable; ppg is nominal (buyable flag).
    ENTERPRISE_PPG = float(os.environ.get('ENTERPRISE_PPG', '1.0'))
    # Refresh the enterprise cache at most this often (seconds).
    TTL = float(os.environ.get('ENTERPRISE_TTL', '30'))

    def __init__(self, use_db=False, BUYABLES_DB=None):

        self.BUYABLES_DB = BUYABLES_DB
        self.use_db = use_db
        self.prices = defaultdict(float)  # default 0 ppg means not buyable
        # Enterprise material library cache: key = canonical smiles.
        self._enterprise = defaultdict(float)
        self._enterprise_loaded_at = 0.0
        self._enterprise_enabled = True
        # gevent 环境下多个 greenlet 可能并发触发刷新，用锁串行化加载。
        self._enterprise_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Enterprise material library (live PostgreSQL, TTL-cached)
    # ------------------------------------------------------------------
    def _load_enterprise(self):
        """Load/refresh the enterprise material library into the cache.

        Falls back to an empty set (and issues a warning) if the database is
        unreachable so the standard flat file remains the fallback source.
        """
        with self._enterprise_lock:
            self._load_enterprise_unlocked()

    def _load_enterprise_unlocked(self):
        try:
            import psycopg2
        except Exception as e:  # pragma: no cover - driver missing
            MyLogger.print_and_log(
                'psycopg2 not available, enterprise library disabled: {}'.format(e), pricer_loc)
            self._enterprise = defaultdict(float)
            self._enterprise_enabled = False
            return

        q = ("SELECT smiles FROM {} "
             "WHERE smiles IS NOT NULL AND length(trim(smiles)) > 0").format(self.ENTERPRISE_DB['table'])
        try:
            conn = psycopg2.connect(
                host=self.ENTERPRISE_DB['host'],
                port=self.ENTERPRISE_DB['port'],
                dbname=self.ENTERPRISE_DB['dbname'],
                user=self.ENTERPRISE_DB['user'],
                password=self.ENTERPRISE_DB['password'],
                connect_timeout=3,
            )
            cur = conn.cursor()
            cur.execute(q)
            rows = cur.fetchall()
            cur.close()
            conn.close()
        except Exception as e:
            MyLogger.print_and_log(
                'Enterprise material library unavailable, using flat file only: {}'.format(e),
                pricer_loc)
            self._enterprise = defaultdict(float)
            # 失败也打时间戳：走冷却期，避免每次 lookup 都触发 3s 连接超时阻塞
            self._enterprise_loaded_at = time.time()
            return

        new_c = defaultdict(float)
        for (smiles,) in rows:
            smi = canonical_smiles(str(smiles).strip())
            if smi and smi not in EXCLUDE_SMILES:
                new_c[smi] = self.ENTERPRISE_PPG
        self._enterprise = new_c
        self._enterprise_loaded_at = time.time()
        MyLogger.print_and_log(
            'Loaded {} enterprise materials into buyable cache'.format(len(new_c)), pricer_loc)

    def _refresh_enterprise_if_stale(self):
        if not self._enterprise_enabled:
            return
        if enterprise_refresh_due(self._enterprise_loaded_at, self.TTL):
            self._load_enterprise()

    # ------------------------------------------------------------------
    # Standard loading (MongoDB or flat file)
    # ------------------------------------------------------------------
    def load(self, file_name=gc.BUYABLES['file_name']):
        '''
        Load pricer information. Either create connection to MongoDB or load from local file.
        If connection to MongoDB cannot be made, fallback and try to load from local file.
        '''
        if self.use_db:
            self.load_databases()
            return

        if not os.path.isfile(file_name):
            MyLogger.print_and_log('Buyables file does not exist file: {}'.format(file_name), pricer_loc)
            return

        self.load_from_file(file_name)
        # Load the enterprise material library as the higher-priority source.
        self._load_enterprise()

    def load_databases(self):
        '''
        Load the pricing data from the online database
        '''
        db_client = MongoClient(
            gc.MONGO['path'],
            gc.MONGO['id'],
            connect=gc.MONGO['connect'],
            serverSelectionTimeoutMS=1000
        )

        try:
            db_client.server_info()
        except errors.ServerSelectionTimeoutError:
            MyLogger.print_and_log('Cannot connect to mongodb to load prices', pricer_loc)
            self.use_db = False
            self.load()
            return

        db = db_client[gc.BUYABLES['database']]
        self.BUYABLES_DB = db[gc.BUYABLES['collection']]

    def dump_to_file(self, file_path):
        '''
        Write prices to a local file
        '''
        prices = []
        for k, v in self.prices.items():
            tmp = v.copy()
            tmp['smiles'] = k
            prices.append(tmp)

        with gzip.open(file_path, 'wb') as f:
            json.dump(prices, f)

    def load_from_file(self, file_name):
        '''
        Load buyables information from local file
        '''
        with gzip.open(file_name, 'rb') as f:
            prices = json.loads(f.read().decode('utf-8'))

        for p in prices:
            smiles = p.pop('smiles', '')
            if smiles:
                self.prices[smiles] = p.pop('ppg')
        MyLogger.print_and_log('Loaded prices from flat file', pricer_loc)

    def lookup_smiles(self, smiles, alreadyCanonical=False, isomericSmiles=True):
        '''
        Looks up a price by SMILES. Canonicalize smiles string unless
        the user specifies that the smiles string is definitely already
        canonical. If the DB connection does not exist, look up from
        prices dictionary attribute, otherwise lookup from DB.
        If multiple entries exist in the DB, return the lowest price.

        Priority: enterprise material library first, then the standard
        ASKCOS flat file.
        '''
        if not alreadyCanonical:
            mol = Chem.MolFromSmiles(smiles)
            if not mol:
                return 0.
            smiles = Chem.MolToSmiles(mol, isomericSmiles=isomericSmiles)

        if self.use_db:
            ppg = self.enterprise_lookup(smiles)
            if ppg:
                return ppg
            cursor = self.BUYABLES_DB.find({
                'smiles': smiles,
                'source': {'$ne': 'LN'}
            })
            if cursor.count():
                return min([doc['ppg'] for doc in cursor])
            else:
                return 0.
        else:
            ppg = self.enterprise_lookup(smiles)
            if ppg:
                return ppg
            return self.prices[smiles]

    def enterprise_lookup(self, smiles):
        """Return the enterprise ppg for a canonical smiles, or 0.0 if absent.

        Refreshes the TTL cache lazily on first call / after TTL expiry.
        """
        self._refresh_enterprise_if_stale()
        return self._enterprise.get(smiles, 0.0)


if __name__ == '__main__':
    pricer = Pricer()
    pricer.load()
    print('enterprise count:', len(pricer._enterprise))
    print(pricer.lookup_smiles('CCCCCO'))
    print(pricer.lookup_smiles('CCCCXCCO'))