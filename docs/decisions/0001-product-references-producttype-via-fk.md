# 0001. Product references ProductType via ForeignKey (not model inheritance)

- **Status:** Accepted
- **Date:** 2026-06-01

## Context
The domain describes a `Product` as a catalog entry that "inherits from" a
`ProductType` template. `ProductType` carries a dynamic `attribute_schema`
(a JSON list of attribute definitions with boolean flags such as `visible`
and `required`). We needed to decide how this "inherits from" relationship is
realized in Django.

Two readings of "inherits":
1. Django **model inheritance** (`Product(ProductType)`) — a database-level
   subclass relationship.
2. A **template/instance** relationship — many products share one reusable
   type definition.

## Decision
Model the relationship as a `ForeignKey` from `Product` to `ProductType`
(`Product.product_type`, `on_delete=PROTECT`). The product stores its own
concrete attribute values in a separate `attributes` JSON field, validated
against the type's `attribute_schema`.

## Consequences
- One `ProductType` can be reused by many products — matches "template".
- The dynamic attribute schema lives in one place per type; products only
  store values, avoiding schema duplication.
- `PROTECT` prevents deleting a type that still has products attached.
- Validation of `Product.attributes` against `ProductType.attribute_schema`
  is application logic we must implement (not enforced by the DB).

## Alternatives considered
- **Django multi-table inheritance:** would couple each product to a rigid
  set of typed columns and make the "dynamic, per-type attributes" goal
  awkward; schema changes would require migrations rather than data edits.
  Rejected in favor of the flexible template + JSON-schema approach.
