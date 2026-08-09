"""Patch tree_builder.py so a buyable target that has no valid multi-step route
still returns a trivial "buy directly" tree.

Background: the MCTS coordinator sets the `terminal` flag only on chemicals
produced from reaction precursors. The *target* molecule's own buyability is
never marked terminal, so if the target is buyable but cannot be built from
buyable precursors within max_depth, `return_trees()` yields nothing and the
treebuilder API returns `trees: []`. This made buyable business monomers such as
lactic acid, adipic acid, hexamethylenediamine, epsilon-caprolactone and
bisphenol A (all directly purchasable) report "no_tree".

Fix: in `get_buyable_paths`, if `return_trees()` is empty but the target is a
terminal node (buyable with ppg <= max_ppg), mark it terminal and re-collect so
a trivial route (the target itself) is returned. This only adds the fallback
when no reaction route exists, so existing routes (e.g. THF -> BDO) are kept.

Idempotent: safe to run multiple times and on already-patched files.
"""
from __future__ import print_function

TARGET = "/usr/local/ASKCOS/makeit/retrosynthetic/mcts/tree_builder.py"

MARKER = "        # batteryemcl: buyable-target trivial route fallback"
OLD = "        return self.return_trees()"
NEW = (
    MARKER + "\n"
    # NOTE: return_trees() returns a (tree_status, trees) TUPLE. The fallback
    # must unpack it; treating the whole tuple as the tree list makes
    # `if not trees` always False (the fallback never triggers) and breaks the
    # API contract (''tuple' object has no attribute 'keys'').
    "        status, trees = self.return_trees()\n"
    "        if not trees and self.is_a_terminal_node(\n"
    "                self.smiles, self.Chemicals[self.smiles].purchase_price, None):\n"
    "            self.Chemicals[self.smiles].terminal = True\n"
    "            self.Chemicals[self.smiles].set_price(1)\n"
    "            status, trees = self.return_trees()\n"
    "        return (status, trees)"
)


def main():
    with open(TARGET, "r") as fh:
        src = fh.read()
    if MARKER in src:
        print("already patched; nothing to do")
        return
    if src.count(OLD) != 1:
        raise SystemExit("expected exactly one '{}', found {}".format(
            OLD, src.count(OLD)))
    src = src.replace(OLD, NEW)
    with open(TARGET, "w") as fh:
        fh.write(src)
    print("patched {} (added buyable-target trivial-route fallback)".format(TARGET))


if __name__ == "__main__":
    main()