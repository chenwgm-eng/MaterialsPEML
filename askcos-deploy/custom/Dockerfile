# Custom ASKCOS image that switches the retrosynthetic template source to the
# public-domain USPTO-derived templates.
#
#   * global_config.py : points RETRO_TEMPLATES['collection'] at the
#     independent `retro_templates_commercial` collection (default Reaxys data
#     is left untouched).
#   * tb_c_worker.py    : overrides TemplateRelevanceAPIModel.predict() so the
#     treebuilder ranks templates by reaction frequency instead of calling the
#     Reaxys-bound template-relevance TF-Serving model (whose indices no longer
#     align with the swapped-in collection).
#
# Build:  docker build -t batteryemcl/askcos:uspto .
FROM askcos/askcos:latest

COPY patches/makeit/global_config.py \
    /usr/local/ASKCOS/makeit/global_config.py
COPY patches/makeit/utilities/buyable/pricer.py \
    /usr/local/ASKCOS/makeit/utilities/buyable/pricer.py
COPY patches/makeit/utilities/buyable/buyables_exclusions.py \
    /usr/local/ASKCOS/makeit/utilities/buyable/buyables_exclusions.py
COPY patches/treebuilder/tb_c_worker.py \
    /usr/local/ASKCOS/askcos/askcos_site/askcos_celery/treebuilder/tb_c_worker.py
COPY patches/treebuilder/patch_tree_builder.py \
    /usr/local/ASKCOS/patch_tree_builder.py

# psycopg2 2.8.x is the last line supporting the base image's Python 3.5.
# It lets the Pricer query the enterprise material library (PostgreSQL) live.
RUN pip install --upgrade 'psycopg2-binary==2.8.6'

# Remove stale bytecode so the patched modules are recompiled on start.
RUN find /usr/local/ASKCOS -name '*.pyc' -path '*treebuilder*' -delete \
 && find /usr/local/ASKCOS -name '__pycache__' -path '*treebuilder*' -type d -prune -exec rm -rf {} + \
 && find /usr/local/ASKCOS -name '*.pyc' -path '*buyable*' -delete \
 && find /usr/local/ASKCOS -name '__pycache__' -path '*buyable*' -type d -prune -exec rm -rf {} +

# Apply the buyable-target trivial-route fallback to the MCTS tree builder.
RUN python /usr/local/ASKCOS/patch_tree_builder.py