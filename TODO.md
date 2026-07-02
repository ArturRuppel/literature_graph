# TODO — viewer (paper-centric column view)

Open requests for the `lit build` viewer. Details deliberately left thin for now.

- [ ] **Iterative expansion.** Expansion should drill in level by level, not jump straight
  to a single fixed level. (Spec the levels later.)

- [ ] **Specifically link context claims.** A context/lateral claim must show *which claim
  belongs to which paper* — resolve the link to the specific claim, not just the container.

- [ ] **Non-exclusive expansion.** Expanding one paper must not collapse another. Multiple
  papers stay open at once.

- [ ] **Make substructure visible.** Within an expanded paper the slices currently render as
  a flat list (e.g. the methods of `Ruppel2023eLife`), but the graph has a dependency
  hierarchy among them — that hierarchy must be shown.
