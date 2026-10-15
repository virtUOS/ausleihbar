# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

"""Shop navigation by categories (#78, ADR-0011).

Section → Category → Subcategory (any depth) → Product. Everything here works
on one flat category query plus one product-link query per request, so list
endpoints never walk ``Category.ancestors()`` / ``depth`` (one query per
level) and never count per section or per category (#63).
"""
from collections import defaultdict

from accounts import roles
from accounts.eligibility import visible_products

from .models import Category, Product, ProductSet, Section


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
    """Category tree + the requester's visible product and set links, per
    request.

    ``links`` maps a category id to the ids of the products *directly* in it
    that the requester may see (``visible_products``); ``set_links`` likewise
    the live sets whose pool is active and eligible for the requester (#93
    follow-up). Product and set objects are loaded on demand (``preload``) and
    cached, so serializing several sections or categories costs one product
    and one set query when preloaded together.
    """

    def __init__(self, user, pool_ids):
        self.tree = CategoryTree()
        # Borrowers don't see categories without a visible product (whole
        # subtree) — names used only in restricted pools must not leak.
        # Admins and lenders see the whole tree, empty nodes included.
        self.show_empty = roles.is_lender(user)
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
        # ``pool_ids`` (eligible_pool_ids) holds active, live pools only.
        self.set_links = defaultdict(set)
        set_rows = ProductSet.categories.through.objects.filter(
            category__deleted_at__isnull=True,
            productset__deleted_at__isnull=True,
            productset__resource_pool_id__in=pool_ids,
        ).values_list("category_id", "productset_id")
        for category_id, set_id in set_rows:
            if category_id in self.tree:
                self.set_links[category_id].add(set_id)
        self._products = {}
        self._subtree_products = {}
        self._sets = {}
        self._subtree_sets = {}

    def product_ids(self, cid):
        """Visible products of ``cid``'s whole subtree (deduplicated),
        memoised per category for this request (read-only)."""
        found = self._subtree_products.get(cid)
        if found is None:
            ids = set()
            for node in self.tree.subtree(cid):
                ids |= self.links.get(node, set())
            found = self._subtree_products[cid] = frozenset(ids)
        return found

    def count(self, cid):
        return len(self.product_ids(cid))

    def set_ids(self, cid):
        """Visible sets of ``cid``'s whole subtree (deduplicated), memoised."""
        found = self._subtree_sets.get(cid)
        if found is None:
            ids = set()
            for node in self.tree.subtree(cid):
                ids |= self.set_links.get(node, set())
            found = self._subtree_sets[cid] = frozenset(ids)
        return found

    def set_count(self, cid):
        return len(self.set_ids(cid))

    def is_shown(self, cid):
        """Whether ``cid`` is part of the requester's shop navigation: in the
        tree and, for borrowers, holding at least one visible product or
        set."""
        return cid in self.tree and (
            self.show_empty or self.count(cid) > 0 or self.set_count(cid) > 0
        )

    def shown_children(self, cid):
        return [c for c in self.tree.children.get(cid, []) if self.is_shown(c)]

    def add_products(self, products):
        for product in products:
            self._products.setdefault(product.id, product)

    def preload(self, category_ids):
        """Load the product and set objects of the given categories' subtrees
        that aren't cached yet — one query each (none if all are cached)."""
        wanted, wanted_sets = set(), set()
        for cid in category_ids:
            wanted |= self.product_ids(cid)
            wanted_sets |= self.set_ids(cid)
        missing = wanted - self._products.keys()
        if missing:
            self.add_products(
                Product.objects.filter(id__in=missing).prefetch_related("images")
            )
        missing_sets = wanted_sets - self._sets.keys()
        if missing_sets:
            for product_set in ProductSet.objects.filter(
                id__in=missing_sets
            ).prefetch_related("items__product", "images"):
                self._sets[product_set.id] = product_set

    def ordered_sets(self, cid):
        """The subtree's visible sets by name (deduplicated). Call
        ``preload`` first."""
        found = [self._sets[sid] for sid in self.set_ids(cid) if sid in self._sets]
        found.sort(key=lambda s: (s.name.casefold(), s.id))
        return found

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


def product_category_groups(product_ids):
    """Walk-in grouping (#87): ``{product_id: [{key, label, order}, ...]}``.

    One group per (section, category) a product sits in: label is the section
    title plus the category's name path (``Medien › Kameras › Video``); a
    category whose root is in no section gets the bare path and key
    ``-:<category id>``. ``order`` sorts groups: section position, the root's
    index in that section's ``category_order`` (unlisted roots last), then the
    tree's pre-order index. Trashed categories are skipped; a product without
    a live category gets ``[]``. Four queries for any number of products.
    """
    tree = CategoryTree()
    sections = list(Section.objects.all())
    sections_of_root = defaultdict(list)
    section_rank = {}
    for rank, section in enumerate(sections):
        section_rank[section.id] = rank
    for through_row in Section.categories.through.objects.filter(
        section_id__in=[s.id for s in sections]
    ):
        sections_of_root[through_row.category_id].append(through_row.section_id)
    by_section = {s.id: s for s in sections}

    result = {pid: [] for pid in product_ids}
    rows = Product.categories.through.objects.filter(
        product_id__in=list(product_ids)
    ).values_list("product_id", "category_id")
    for product_id, cid in rows:
        if cid not in tree:
            continue
        path = tree.path_names(cid)
        ancestors = tree.ancestors(cid)
        root_id = ancestors[0].id if ancestors else cid
        index = tree.index(cid)
        owners = sections_of_root.get(root_id) or []
        if not owners:
            result[product_id].append(
                {"key": f"-:{cid}", "label": " › ".join(path),
                 "order": [len(sections), 0, index]}
            )
            continue
        for sid in owners:
            section = by_section[sid]
            listed = list(section.category_order or [])
            root_rank = listed.index(root_id) if root_id in listed else len(listed)
            result[product_id].append(
                {
                    "key": f"{sid}:{cid}",
                    "label": " › ".join([section.title] + path),
                    "order": [section_rank[sid], root_rank, index],
                }
            )
    for groups in result.values():
        groups.sort(key=lambda g: g["order"])
    return result
