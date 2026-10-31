# Railway track for maps: OpenStreetMap

`rail_graph.json` is India's railway lines as a routable graph, used only to draw a train's
path on the journey map (`GET /journeys/{id}/map`).

- **Source:** OpenStreetMap railway lines (`railway=rail`, without yard/siding `service=*`
  tracks), downloaded through the public Overpass API.
- **Licence:** © OpenStreetMap contributors, [Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
  This file is a derived database and is ODbL as well; the map shows the attribution.
- **What it holds:** junction/end/station nodes, merged track edges with shapes simplified to
  about 30 m, and each station with trains snapped to its nearest track (distance in metres).
- **Honest gaps:** where OpenStreetMap has a gap, or the only path is a long detour, the map
  draws a dashed straight line for that stretch and says how much follows the real track.

Base map tiles come from `tile.openstreetmap.org` under the
[OSM tile usage policy](https://operations.osmfoundation.org/policies/tiles/) — fine for a
small app; a busy public service should use its own tile server or a tile provider.

## Rebuild

From `backend/`:

```bash
.venv/bin/python data/tools/fetch_osm_rail.py <scratch_folder>/tiles
python3 -I data/tools/build_rail_graph.py <scratch_folder>/tiles
```

`build_rail_graph.py` also accepts a GeoJSON export (for example HOTOSM's
`hotosm_ind_railways` on HDX), but that export splits lines at district borders and drops
some stretches, so fewer routes follow the track.
