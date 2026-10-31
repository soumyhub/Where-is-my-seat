#!/usr/bin/env python3
"""Generate ``data/simulated/trains.json``.

EVERY TRAIN HERE IS SIMULATED. Numbers use a reserved ``SIM-`` prefix so they can never
be mistaken for real Indian Railways services; names are invented; times and distances
are plausible but made up. Only the station names and codes are real. Use this network to
exercise the route-search algorithm, never as a timetable.

Each stop line is ``CODE  ARR  DEP  KM`` with ``-`` for a missing time. Running days are
computed automatically from the times (a time earlier than the previous one means the
train crossed midnight).

Run from the backend folder:  python data/tools/build_simulated_trains.py
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "simulated" / "trains.json"
DAILY = "daily"
MON_SAT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


def hhmm(value: str) -> int:
    h, m = value.split(":")
    return int(h) * 60 + int(m)


def stops(block: str) -> list[dict]:
    out: list[dict] = []
    day, last = 1, -1
    for line in block.strip().splitlines():
        code, arr, dep, km = line.split()
        row: dict = {"code": code, "km": int(km)}
        if arr != "-":
            minute = (day - 1) * 1440 + hhmm(arr)
            while minute < last:
                day += 1
                minute += 1440
            last = minute
            row["arr"] = arr
        row["day"] = day
        if dep != "-":
            minute = (day - 1) * 1440 + hhmm(dep)
            if minute < last:
                minute += 1440
                day += 1  # departs after midnight; later stops are on the next day
            last = minute
            row["dep"] = dep
        out.append(row)
    return out


def train(number, name, category, classes, block, *, runs=DAILY, superfast=False, unreserved=True):
    return {
        "number": number,
        "name": name,
        "category": category,
        "simulated": True,
        "superfast": superfast,
        "runs_on": runs,
        "classes": classes,
        "unreserved": unreserved,
        "source": "Synthetic demo timetable (build_simulated_trains.py)",
        "stops": stops(block),
    }


TRAINS = [
    # ----- Delhi - Rewari - Alwar - Jaipur - Ajmer corridor ---------------
    train("SIM-1101", "Marigold Mail", "Mail/Express", ["2A", "3A", "SL"], """
        NDLS  -     06:00   0
        DEC   06:22 06:24  14
        GGN   06:48 06:50  32
        RE    07:38 07:40  83
        AWR   08:40 08:43 158
        BKI   09:40 09:42 219
        DO    10:08 10:10 256
        GADJ  10:52 10:54 299
        JP    11:10 11:20 308
        FL    12:05 12:07 362
        KSG   12:52 12:54 412
        AII   13:35 -     443
    """),
    train("SIM-1102", "Marigold Mail", "Mail/Express", ["2A", "3A", "SL"], """
        AII   -     14:30   0
        KSG   15:08 15:10  31
        FL    15:55 15:57  81
        JP    16:45 16:55 135
        GADJ  17:08 17:10 144
        DO    17:52 17:54 187
        BKI   18:20 18:22 224
        AWR   19:20 19:23 285
        RE    20:25 20:27 360
        GGN   21:15 21:17 411
        DEC   21:40 21:42 429
        NDLS  22:10 -     443
    """),
    # Passes Dausa without halting: the engine must never board or alight it there.
    train("SIM-1203", "Sandstone Superfast", "Superfast", ["2A", "3A", "SL"], """
        DEE   -     13:20   0
        DEC   13:36 13:38  10
        GGN   14:02 14:04  28
        RE    14:50 14:52  79
        AWR   15:50 15:53 154
        BKI   16:48 16:50 215
        GADJ  18:02 18:04 295
        JP    18:20 -     304
    """, superfast=True),
    train("SIM-1204", "Sandstone Superfast", "Superfast", ["2A", "3A", "SL"], """
        JP    -     05:45   0
        GADJ  05:58 06:00   9
        BKI   07:08 07:10  89
        AWR   08:05 08:08 150
        RE    09:05 09:07 225
        GGN   09:52 09:54 276
        DEC   10:18 10:20 294
        DEE   10:40 -     304
    """, superfast=True),
    train("SIM-1305", "Peacock Intercity", "Intercity", ["CC", "2S"], """
        NDLS  -     15:10   0
        GGN   15:52 15:54  32
        RE    16:40 16:42  83
        AWR   17:40 17:43 158
        BKI   18:36 18:38 219
        DO    19:02 19:04 256
        GADJ  19:45 19:47 299
        JP    20:00 -     308
    """, runs=MON_SAT, superfast=True),
    train("SIM-1306", "Peacock Intercity", "Intercity", ["CC", "2S"], """
        JP    -     06:30   0
        GADJ  06:42 06:44   9
        DO    07:25 07:27  52
        BKI   07:52 07:54  89
        AWR   08:48 08:51 150
        RE    09:50 09:52 225
        GGN   10:38 10:40 276
        NDLS  11:25 -     308
    """, runs=MON_SAT, superfast=True),
    train("SIM-1407", "Night Kite Express", "Mail/Express", ["1A", "2A", "3A", "SL"], """
        DLI   -     22:40   0
        DEE   22:52 22:55   5
        DEC   23:10 23:12  15
        GGN   23:38 23:40  33
        RE    00:28 00:30  84
        AWR   01:35 01:38 159
        BKI   02:38 02:40 220
        DO    03:06 03:08 257
        GADJ  03:52 03:54 300
        JP    04:10 04:25 309
        FL    05:12 05:14 363
        KSG   06:00 06:02 413
        AII   06:45 -     444
    """),
    train("SIM-1408", "Night Kite Express", "Mail/Express", ["1A", "2A", "3A", "SL"], """
        AII   -     21:00   0
        KSG   21:40 21:42  31
        FL    22:28 22:30  81
        JP    23:20 23:35 135
        GADJ  23:48 23:50 144
        DO    00:32 00:34 187
        BKI   01:00 01:02 224
        AWR   02:00 02:03 285
        RE    03:10 03:12 360
        GGN   04:02 04:04 411
        DEC   04:28 04:30 429
        DEE   04:45 04:47 439
        DLI   05:00 -     444
    """),
    # Rewari - Narnaul - Ringas route into Jaipur
    train("SIM-1509", "Saffron Valley Express", "Mail/Express", ["2A", "3A", "SL"], """
        DEE   -     09:05   0
        DEC   09:21 09:23  10
        GGN   09:48 09:50  28
        RE    10:40 10:45  79
        NNL   11:40 11:42 140
        RGS   13:20 13:22 242
        JP    14:30 -     299
    """),
    train("SIM-1510", "Saffron Valley Express", "Mail/Express", ["2A", "3A", "SL"], """
        JP    -     15:30   0
        RGS   16:38 16:40  57
        NNL   18:15 18:17 159
        RE    19:15 19:20 220
        GGN   20:08 20:10 271
        DEC   20:35 20:37 289
        DEE   20:55 -     299
    """),
    # Delhi - Bandikui - Agra and Agra - Bandikui - Jaipur - Ajmer
    train("SIM-2211", "Ridge Express", "Mail/Express", ["3A", "SL"], """
        NDLS  -     07:15   0
        DEC   07:37 07:39  14
        GGN   08:03 08:05  32
        RE    08:52 08:55  83
        AWR   09:55 09:58 158
        BKI   10:55 10:58 219
        BTE   12:25 12:28 316
        IDH   13:15 13:17 368
        AF    13:30 -     372
    """),
    train("SIM-2212", "Ridge Express", "Mail/Express", ["3A", "SL"], """
        AF    -     14:30   0
        IDH   14:40 14:42   4
        BTE   15:30 15:33  56
        BKI   17:00 17:03 153
        AWR   18:00 18:03 214
        RE    19:05 19:08 289
        GGN   19:55 19:57 340
        DEC   20:20 20:22 358
        NDLS  20:45 -     372
    """),
    train("SIM-2405", "Fort Link Express", "Mail/Express", ["3A", "SL"], """
        AF    -     08:45   0
        IDH   08:55 08:57   4
        BTE   09:50 09:53  56
        BKI   11:35 11:40 153
        DO    12:06 12:08 190
        GADJ  12:50 12:52 233
        JP    13:05 13:15 242
        FL    14:00 14:02 296
        KSG   14:45 14:47 346
        AII   15:20 -     377
    """),
    train("SIM-2406", "Fort Link Express", "Mail/Express", ["3A", "SL"], """
        AII   -     07:40   0
        KSG   08:12 08:14  31
        FL    08:58 09:00  81
        JP    09:50 10:00 135
        GADJ  10:12 10:14 144
        DO    10:55 10:57 187
        BKI   11:25 11:30 224
        BTE   13:10 13:13 321
        IDH   14:00 14:02 373
        AF    14:15 -     377
    """),
    # Leaves Alwar 15 min after SIM-2211 arrives: that connection must be rejected.
    train("SIM-2313", "Alwar Jaipur Link", "Intercity", ["CC", "2S"], """
        AWR   -     10:10   0
        BKI   11:05 11:07  61
        DO    11:32 11:34  98
        GADJ  12:15 12:17 141
        JP    12:30 -     150
    """),
    train("SIM-2314", "Alwar Jaipur Link", "Intercity", ["CC", "2S"], """
        JP    -     16:10   0
        GADJ  16:22 16:24   9
        DO    17:05 17:07  52
        BKI   17:35 17:37  89
        AWR   18:30 -     150
    """),
    train("SIM-3301", "Lotus Link", "Intercity", ["SL", "2S"], """
        JP    -     19:15   0
        FL    20:02 20:04  54
        KSG   20:50 20:52 104
        AII   21:30 -     135
    """),
    train("SIM-3302", "Lotus Link", "Intercity", ["SL", "2S"], """
        AII   -     06:00   0
        KSG   06:38 06:40  31
        FL    07:25 07:27  81
        JP    08:15 -     135
    """),
    # Unreserved MEMU shuttles Delhi <-> Rewari (general tickets only)
    train("SIM-6401", "Delhi Rewari MEMU", "MEMU", [], """
        NDLS  -     05:10   0
        DEC   05:32 05:33  14
        GGN   05:57 05:59  32
        RE    06:50 -      83
    """),
    train("SIM-6403", "Delhi Rewari MEMU", "MEMU", [], """
        NDLS  -     11:50   0
        DEC   12:12 12:13  14
        GGN   12:38 12:40  32
        RE    13:35 -      83
    """),
    train("SIM-6405", "Delhi Rewari MEMU", "MEMU", [], """
        NDLS  -     17:20   0
        DEC   17:42 17:43  14
        GGN   18:07 18:09  32
        RE    19:00 -      83
    """),
    train("SIM-6402", "Rewari Delhi MEMU", "MEMU", [], """
        RE    -     07:30   0
        GGN   08:22 08:24  51
        DEC   08:48 08:49  69
        NDLS  09:15 -      83
    """),
    train("SIM-6404", "Rewari Delhi MEMU", "MEMU", [], """
        RE    -     15:30   0
        GGN   16:22 16:24  51
        DEC   16:48 16:49  69
        NDLS  17:15 -      83
    """),
    # ----- Delhi - Mathura - Sawai Madhopur - Kota corridor ---------------
    train("SIM-1611", "Firefly Night Express", "Superfast", ["1A", "2A", "3A", "SL"], """
        NZM   -     21:45   0
        FDB   22:08 22:10  21
        PWL   22:38 22:40  57
        MTJ   23:50 23:55 141
        BTE   00:30 00:32 175
        BXN   01:10 01:12 223
        GGC   02:05 02:07 290
        SWM   03:00 03:05 356
        KOTA  04:50 -     465
    """, superfast=True),
    train("SIM-1612", "Firefly Night Express", "Superfast", ["1A", "2A", "3A", "SL"], """
        KOTA  -     22:15   0
        SWM   23:55 00:00 109
        GGC   00:50 00:52 175
        BXN   01:45 01:47 242
        BTE   02:25 02:27 290
        MTJ   03:05 03:10 324
        PWL   04:15 04:17 408
        FDB   04:48 04:50 444
        NZM   05:20 -     465
    """, superfast=True),
    train("SIM-1613", "Starling Express", "Mail/Express", ["2A", "3A", "SL"], """
        NZM   -     06:10   0
        FDB   06:32 06:34  21
        PWL   07:05 07:07  57
        MTJ   08:15 08:20 141
        BTE   08:55 08:57 175
        BXN   09:40 09:42 223
        GGC   10:40 10:42 290
        SWM   11:40 11:45 356
        KOTA  13:30 -     465
    """),
    train("SIM-1614", "Starling Express", "Mail/Express", ["2A", "3A", "SL"], """
        KOTA  -     14:20   0
        SWM   16:05 16:10 109
        GGC   17:05 17:07 175
        BXN   18:05 18:07 242
        BTE   18:50 18:52 290
        MTJ   19:30 19:35 324
        PWL   20:40 20:42 408
        FDB   21:12 21:14 444
        NZM   21:40 -     465
    """),
    train("SIM-1715", "Bulbul Express", "Mail/Express", ["3A", "SL"], """
        JP    -     02:40   0
        DPA   02:52 02:54   7
        SWM   05:00 05:10 131
        KOTA  06:50 -     240
    """),
    train("SIM-1716", "Bulbul Express", "Mail/Express", ["3A", "SL"], """
        KOTA  -     18:30   0
        SWM   20:15 20:20 109
        DPA   22:25 22:27 233
        JP    22:40 -     240
    """),
    train("SIM-1817", "Tiger Trail Intercity", "Intercity", ["CC", "2S"], """
        SWM   -     06:00   0
        DPA   08:05 08:07 124
        JP    08:25 -     131
    """),
    train("SIM-1818", "Tiger Trail Intercity", "Intercity", ["CC", "2S"], """
        JP    -     17:30   0
        DPA   17:42 17:44   7
        SWM   19:50 -     131
    """),
    train("SIM-1901", "Yamuna Link", "Intercity", ["CC", "2S"], """
        NZM   -     07:00   0
        FDB   07:20 07:22  21
        PWL   07:48 07:50  57
        MTJ   08:50 08:53 141
        AGC   09:45 -     195
    """, superfast=True),
    train("SIM-1902", "Yamuna Link", "Intercity", ["CC", "2S"], """
        AGC   -     18:30   0
        MTJ   19:22 19:25  54
        PWL   20:25 20:27 138
        FDB   20:55 20:57 174
        NZM   21:20 -     195
    """, superfast=True),
]


def main() -> None:
    doc = {
        "meta": {
            "simulated": True,
            "version": "2026.10-demo1",
            "last_updated": "2026-10-30",
            "source": "Synthetic demo timetable (build_simulated_trains.py)",
            "disclaimer": (
                "SIMULATED. Train numbers (SIM-xxxx), names, times, days and distances are invented "
                "for algorithm testing. They are not Indian Railways services or an official timetable."
            ),
        },
        "trains": TRAINS,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {len(TRAINS)} simulated trains to {OUT}")


if __name__ == "__main__":
    main()
