# Undocumented behavior notes

The detailed implementation guidance is maintained in
[z80-undocumented-behavior.md](z80-undocumented-behavior.md). It covers the
modeled Q register, WZ/MEMPTR, refresh-state effects, and undocumented X/Y flag
rules that are observed by the pinned vector corpus.

For semantic changes, treat the vectors as the ground truth and run the full
vector gate after updating focused regression tests.
