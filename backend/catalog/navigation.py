# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Shop navigation by categories (#78, ADR-0011).

Section → Category → Subcategory (any depth) → Product. Everything here works
on one flat category query plus one product-link query per request, so list
endpoints never walk ``Category.ancestors()`` / ``depth`` (one query per
level) and never count per section or per category (#63).
"""
from collections import defaultdict

from accounts.eligibility import visible_products

from .models import Category, Product


def daily_first(products):
    """#19: daily products before hourly ones; a stable sort, so each block
    keeps its incoming (curated) order."""
    return sorted(products, key=lambda p: p.lending_type != Product.LendingType.DAYS)


class CategoryTree:
    """The live category tree, built from a single flat query.

    Only categories reachable from a live top-level category are part of the
    tree; a live category below a trashed parent is unreachable and hidden.
    Siblings are ordered by ``position``, then name.
    """

    def __init__(self, categories=None):
        rows = list(categories if categories is not None else Category.objects.all())
        rows.sort(key=lambda c: (c.position, (c.name or "").casefold(), c.id))
        by_id = {c.id: c for c in rows}
        children = defaultdict(list)
        for category in rows:
            children[category.parent_id].append(category.id)
        # Pre-order walk from the roots; a cycle can't be reached from a root.
        self.order = []
        stack = list(reversed(children[None]))
        while stack:
            cid = stack.pop()
            self.order.append(cid)
            stack.extend(reversed(children[cid]))
        self.nodes = {cid: by_id[cid] for cid in self.order}
        self.children = {cid: children[cid] for cid in self.order}
        self.roots = list(children[None])
        self._index = {cid: i for i, cid in enumerate(self.order)}

    def __contains__(self, cid):
        return cid in self.nodes

    def index(self, cid):
        """Position of ``cid`` in the tree's pre-order (for sorting)."""
        return self._index[cid]

    def subtree(self, cid):
        """``cid`` and all its descendants, in pre-order (empty if unknown)."""
        if cid not in self.nodes:
            return []
        out, stack = [], [cid]
        while stack:
            node = stack.pop()
            out.append(node)
            stack.extend(reversed(self.children[node]))
        return out

    def subtree_of_all(self, cids):
        """Union of the subtrees of ``cids`` (ids)."""
        found = set()
        for cid in cids:
            found.update(self.subtree(cid))
        return found

    def ancestors(self, cid):
        """Ancestor categories from the root down to the direct parent."""
        chain = []
        node = self.nodes.get(cid)
        while node is not None and node.parent_id is not None:
            node = self.nodes.get(node.parent_id)
            if node is None:
                break
            chain.append(node)
        return list(reversed(chain))

    def depth(self, cid):
        return len(self.ancestors(cid))

    def path_names(self, cid):
        """Names from the root down to ``cid`` itself."""
        return [c.name for c in self.ancestors(cid)] + [self.nodes[cid].name]


class ShopNavigation:
    """Category tree + the requester's visible product links, per request.

    ``links`` maps a category id to the ids of the products *directly* in it
    that the requester may see (``visible_products``). Product objects are
    loaded on demand (``preload``) and cached, so serializing several sections
    or categories costs one product query when preloaded together.
    """

    def __init__(self, user, pool_ids):
        self.tree = CategoryTree()
        # Borrowers don't see categories without a visible product (whole
        # subtree) — names used only in restricted pools must not leak.
        # Staff and lenders see the whole tree, empty nodes included.
        self.show_empty = bool(
            user is not None
            and user.is_authenticated
            and (
                user.is_staff
                or user.is_superuser
                or user.pool_memberships.exists()
            )
        )
        visible = visible_products(
            Product.objects.all(), user, pool_ids=pool_ids
        ).values("id")
        through = Product.categories.through
        self.links = defaultdict(set)
        rows = through.objects.filter(
            category__deleted_at__isnull=True, product_id__in=visible
        ).values_list("category_id", "product_id")
        for category_id, product_id in rows:
            if category_id in self.tree:
                self.links[category_id].add(product_id)
        self._products = {}

    def product_ids(self, cid):
        """Visible products of ``cid``'s whole subtree (deduplicated)."""
        found = set()
        for node in self.tree.subtree(cid):
            found |= self.links.get(node, set())
        return found

    def count(self, cid):
        return len(self.product_ids(cid))

    def is_shown(self, cid):
        """Whether ``cid`` is part of the requester's shop navigation: in the
        tree and, for borrowers, holding at least one visible product."""
        return cid in self.tree and (self.show_empty or self.count(cid) > 0)

    def shown_children(self, cid):
        return [c for c in self.tree.children.get(cid, []) if self.is_shown(c)]

    def add_products(self, products):
        for product in products:
            self._products.setdefault(product.id, product)

    def preload(self, category_ids):
        """Load the product objects of the given categories' subtrees that
        aren't cached yet — one query (none if all are cached)."""
        wanted = set()
        for cid in category_ids:
            wanted |= self.product_ids(cid)
        missing = wanted - self._products.keys()
        if missing:
            self.add_products(
                Product.objects.filter(id__in=missing).prefetch_related("images")
            )

    def ordered_products(self, cid, restrict=None):
        """The subtree's products in shop order: walking the subtree in
        pre-order, each category's own products by its ``product_order`` (then
        title), skipping products already listed higher up; finally daily
        before hourly (#19). ``restrict`` (ids) narrows the set, e.g. to one
        pool's products. Call ``preload`` (or ``add_products``) first."""
        seen, out = set(), []
        for node_id in self.tree.subtree(cid):
            node = self.tree.nodes[node_id]
            rank = {pid: i for i, pid in enumerate(node.product_order or [])}
            direct = [
                self._products[pid]
                for pid in self.links.get(node_id, ())
                if pid not in seen
                and pid in self._products
                and (restrict is None or pid in restrict)
            ]
            direct.sort(key=lambda p: (rank.get(p.id, len(rank)), p.title.casefold(), p.id))
            for product in direct:
                seen.add(product.id)
                out.append(product)
        return daily_first(out)

    def section_roots(self, section):
        """The section's live top-level categories in its ``category_order``
        (unlisted after, in tree order). Uses ``section.categories.all()`` —
        prefetch it when serializing several sections."""
        rank = {cid: i for i, cid in enumerate(section.category_order or [])}
        roots = [
            c.id for c in section.categories.all()
            if c.parent_id is None and self.is_shown(c.id)
        ]
        roots.sort(key=lambda cid: (rank.get(cid, len(rank)), self.tree.index(cid)))
        return roots
