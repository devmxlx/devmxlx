# Profile graphics

The header, toolkit and activity graphics follow the public visual language of [mxlx.studio](https://mxlx.studio): light gray surfaces, black typography, compact section numbers, a pixel asterisk and lime green accents.

`python3 scripts/render_brand.py` rebuilds the header, toolkit and spoken-language graphics. Activity, streak and code-language renderers live in `scripts/update_stats.py` and refresh together. SVGs have accessible titles and descriptions, use native vector text/shapes and require no external font or statistics service.

The obsidian graphic and original asterisk PNG were taken from the owner's agency website for the owner's GitHub profile:

- [Obsidian graphic](https://framerusercontent.com/images/yypqFfafaPtn9wB6Ll8chJoNbA.png)
- [Original asterisk](https://framerusercontent.com/images/vd0bSzT5O866riKolkXi4mmi1o.png)

The header embeds the obsidian PNG directly in its SVG; the pixel asterisk is recreated as SVG geometry. No remote image request is needed when the SVG is displayed.
