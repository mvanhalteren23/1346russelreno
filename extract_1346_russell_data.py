#!/usr/bin/env python3
"""
Extracts the 3D DAM photogrammetry mesh, 68 architectural wall edges & openings,
room bounds, and 24 indoor 360° panorama sweeps from the Matterport scan of
1346 Russell Road, Gibsons (Model ID: rfwtuskak8Q) into assets/house_data.js.
"""

import json
import os
import struct

BASE_DIR = "/home/antigravity/Matterport-/downloads/rfwtuskak8Q"
OUT_JS = "/home/antigravity/Matterport-/assets/house_data.js"
DAM_PATH = f"{BASE_DIR}/models/fe99fc8f47a44afcb9689604fc0b42da/assets/eb9d0e89e20144eab2598553bedda84a_50k.dam"


def read_varint(b: bytes, pos: int):
    res, shift = 0, 0
    while True:
        byte = b[pos]
        pos += 1
        res |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return res, pos
        shift += 7


def parse_msg(b: bytes, start: int, end: int):
    pos, fields = start, []
    while pos < end:
        tag, pos = read_varint(b, pos)
        fn, wt = tag >> 3, tag & 7
        if wt == 0:
            v, pos = read_varint(b, pos)
            fields.append((fn, "varint", v))
        elif wt == 2:
            l, pos = read_varint(b, pos)
            fields.append((fn, "bytes", l, pos, pos + l))
            pos += l
        elif wt == 5:
            val = struct.unpack("<f", b[pos : pos + 4])[0]
            pos += 4
            fields.append((fn, "f32", val))
        else:
            break
    return fields


def classify_triangle_zone(cx: float, cy: float, cz: float, is_indoor_chunk: bool) -> str:
    # Roof / upper ceiling cutaway zone
    if cz > 0.85:
        if 1.8 <= cy <= 9.0 and 2.3 <= cx <= 11.8:
            return "ceiling_vaulted"
        return "ceiling_flat"
    if not is_indoor_chunk:
        return "exterior"
    # Kitchen U-peninsula & suspended chain cabinet (x: 4.5..7.9, y: -5.2..-2.8)
    if 4.4 <= cx <= 7.95 and -5.25 <= cy <= -2.85 and cz > -1.08:
        return "kitchen_peninsula"
    # Kitchen south & east perimeter cabinets / brick oven column
    if 2.35 <= cx <= 8.55 and -6.05 <= cy <= -4.85 and cz > -1.08:
        return "kitchen_perimeter"
    # Central hallway closet block (x: 6.60..7.58, y: -3.05..-0.58)
    if 6.58 <= cx <= 7.58 and -3.08 <= cy <= -0.58 and cz > -1.08:
        return "hallway_closet"
    # Living Room / Office half-wall (pony wall) at x: 7.20..7.72, y: 3.35..8.55
    if 7.18 <= cx <= 7.75 and 3.35 <= cy <= 8.55 and -1.08 < cz < 0.45:
        return "office_pony_wall"
    # Diagonal brick fireplace at x: 6.25..7.55, y: 1.85..3.45
    if 6.25 <= cx <= 7.58 and 1.85 <= cy <= 3.45 and cz > -1.10:
        return "fireplace"
    # Office / Bedroom 2 wall at y ~ 3.36, x: 7.43..11.63
    if 7.45 <= cx <= 11.65 and 3.18 <= cy <= 3.58 and cz > -1.08:
        return "wall_office_bed2"
    # Kitchen / Laundry-Storage wall at y ~ -6.00, x: 8.50..11.80
    if 8.45 <= cx <= 11.82 and -6.20 <= cy <= -5.80 and cz > -1.08:
        return "wall_kitchen_laundry"
    # Bathroom interior (x: 8.50..11.78, y: -1.95..0.40)
    if 8.50 <= cx <= 11.78 and -1.96 <= cy <= 0.40 and cz > -1.08:
        return "bathroom"
    if cz <= -0.92:
        return "floor"
    return "walls_general"


def classify_wall_edge(idx: int, x0: float, y0: float, x1: float, y1: float) -> dict:
    mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    # Central hallway closet block: x in [6.65, 7.55], y in [-3.0, -0.6]
    if 6.65 <= mx <= 7.55 and -3.05 <= my <= -0.60:
        return {"group": "hallway_closet", "label": "Hallway Central Closet Wall", "removable": True}
    # Diagonal fireplace box: x in [6.35, 7.50], y in [1.90, 3.40]
    if 6.35 <= mx <= 7.50 and 1.90 <= my <= 3.40:
        return {"group": "fireplace", "label": "Living Room Brick Fireplace", "removable": True}
    # Kitchen peninsula stub wall (E54): x in [3.1, 4.2], y ~ -3.0
    if 3.1 <= mx <= 4.2 and -3.15 <= my <= -2.85:
        return {"group": "kitchen_peninsula", "label": "Kitchen / Dining Divider Wall", "removable": True}
    # Wall between Office and Bedroom 2 (E49): x in [7.4, 11.7], y ~ 3.37
    if 7.35 <= mx <= 11.70 and 3.25 <= my <= 3.50 and dy < 0.3:
        return {"group": "wall_office_bed2", "label": "Office / Bedroom 2 Partition Wall", "removable": True}
    # Wall between Kitchen/Bedroom 1 and Storage/Laundry (y ~ -6.0)
    if 8.50 <= mx <= 11.82 and -6.15 <= my <= -5.85 and dy < 0.3:
        return {"group": "wall_kitchen_laundry", "label": "Bedroom 1 & Kitchen / Laundry-Storage Wall", "removable": True}
    # Storage room internal walls (x in [8.5, 10.6], y in [-7.8, -5.9])
    if 8.50 <= mx <= 10.65 and -7.80 <= my <= -5.90 and mx < 11.5:
        return {"group": "storage_walls", "label": "Storage Closet Partition Wall", "removable": True}
    # Bedroom 2 / Bathroom & Closet walls (y in [-0.5, 0.5], x in [6.4, 11.7])
    if 6.40 <= mx <= 11.70 and -0.55 <= my <= 0.80:
        return {"group": "wall_bed2_bath", "label": "Bedroom 2 / Bathroom & Hallway Wall", "removable": True}
    # Bathroom / Bedroom 1 walls (y in [-2.0, -1.3], x in [8.5, 11.7])
    if 8.45 <= mx <= 11.75 and -2.05 <= my <= -1.30:
        return {"group": "wall_bath_bed1", "label": "Bathroom / Bedroom 1 Wall", "removable": True}
    # Bedroom 1 closet & hallway walls (x in [8.3, 10.6], y in [-5.4, -1.9])
    if 8.25 <= mx <= 10.65 and -5.40 <= my <= -1.90:
        return {"group": "wall_bed1_hall", "label": "Bedroom 1 Closet & Hallway Wall", "removable": True}
    return {"group": "exterior_structural", "label": "Exterior Perimeter Wall", "removable": False}


def main():
    with open(DAM_PATH, "rb") as f:
        buf = f.read()

    top = parse_msg(buf, 0, len(buf))
    target_chunks = {
        1: ("tex_000.jpg", True, "Bedroom 2 Scan"),
        3: ("tex_001.jpg", True, "Living/Office Vault Scan"),
        29: ("tex_023.jpg", True, "Bedroom 1 Scan"),
        30: ("tex_023.jpg", True, "Laundry & Storage Scan"),
        197: ("tex_181.jpg", True, "Main House Interior Scan"),
        4: ("tex_002.jpg", False, "Carport & South Exterior"),
        7: ("tex_005.jpg", False, "South Entry & Yard"),
        8: ("tex_006.jpg", False, "Southwest Lawn & Roof"),
        31: ("tex_024.jpg", False, "East Carport Roof"),
        32: ("tex_025.jpg", False, "Northeast Exterior"),
        45: ("tex_038.jpg", False, "North Roof & Office Exterior"),
        110: ("tex_097.jpg", False, "Main Gable Roof"),
        120: ("tex_107.jpg", False, "Kitchen & Carport Roof"),
    }

    mesh_chunks = []
    for cidx, (tex_file, is_indoor, label) in target_chunks.items():
        sub = parse_msg(buf, top[cidx][3], top[cidx][4])
        v_sub = parse_msg(buf, sub[0][3], sub[0][4])
        v_bytes = buf[v_sub[0][3] : v_sub[0][4]]
        uv_bytes = buf[v_sub[1][3] : v_sub[1][4]]
        n_verts = len(v_bytes) // 12
        verts = struct.unpack(f"<{n_verts * 3}f", v_bytes)
        uvs = struct.unpack(f"<{n_verts * 2}f", uv_bytes)

        i_sub = parse_msg(buf, sub[1][3], sub[1][4])
        ibuf_start, ibuf_end = i_sub[0][3], i_sub[0][4]
        pos = ibuf_start
        raw_indices = []
        while pos < ibuf_end:
            v, pos = read_varint(buf, pos)
            raw_indices.append(v)

        # Filter triangles for outdoor chunks so we only keep the house & carport envelope
        remap = {}
        out_verts = []
        out_uvs = []
        out_indices = []
        tri_zones = []

        for t in range(0, len(raw_indices), 3):
            i0, i1, i2 = raw_indices[t], raw_indices[t + 1], raw_indices[t + 2]
            x0, y0, z0 = verts[3 * i0], verts[3 * i0 + 1], verts[3 * i0 + 2]
            x1, y1, z1 = verts[3 * i1], verts[3 * i1 + 1], verts[3 * i1 + 2]
            x2, y2, z2 = verts[3 * i2], verts[3 * i2 + 1], verts[3 * i2 + 2]
            cx, cy, cz = (x0 + x1 + x2) / 3.0, (y0 + y1 + y2) / 3.0, (z0 + z1 + z2) / 3.0

            if not is_indoor:
                if not (0.5 <= cx <= 13.5 and -12.5 <= cy <= 10.2):
                    continue

            new_tri = []
            for old_i in (i0, i1, i2):
                if old_i not in remap:
                    remap[old_i] = len(out_verts) // 3
                    out_verts.extend([round(verts[3 * old_i], 4), round(verts[3 * old_i + 1], 4), round(verts[3 * old_i + 2], 4)])
                    out_uvs.extend([round(uvs[2 * old_i], 4), round(uvs[2 * old_i + 1], 4)])
                new_tri.append(remap[old_i])
            out_indices.extend(new_tri)
            tri_zones.append(classify_triangle_zone(cx, cy, cz, is_indoor))

        if out_indices:
            mesh_chunks.append({
                "chunkId": cidx,
                "label": label,
                "texture": tex_file,
                "isIndoor": is_indoor,
                "positions": out_verts,
                "uvs": out_uvs,
                "indices": out_indices,
                "triZones": tri_zones,
            })
            print(f"Chunk {cidx} ({label}): {len(out_verts)//3} verts, {len(out_indices)//3} tris")

    # 2. Extract 68 walls and openings from GetRoomBounds.json
    with open(f"{BASE_DIR}/api/mp/models/graph_GetRoomBounds.json") as f:
        rb = json.load(f)["data"]["model"]

    walls = []
    for idx, e in enumerate(rb["floors"][1]["edges"]):
        v0 = e["vertices"][0]["position"]
        v1 = e["vertices"][1]["position"]
        x0, y0 = round(v0["x"], 4), round(v0["y"], 4)
        x1, y1 = round(v1["x"], 4), round(v1["y"], 4)
        meta = classify_wall_edge(idx, x0, y0, x1, y1)
        ops = []
        for o in e.get("openings", []):
            ops.append({
                "id": o["id"],
                "type": o["type"],
                "width": round(o["width"], 3),
                "relativeCenter": round(o["relativeCenter"], 3),
                "height": round(o["height"], 3),
                "lowerElevation": round(o["lowerElevation"], 3),
            })
        walls.append({
            "index": idx,
            "id": e["id"],
            "x0": x0,
            "y0": y0,
            "x1": x1,
            "y1": y1,
            "thickness": round(e["thickness"], 3),
            "bias": round(e.get("centerLineBias", 0.5), 3),
            "openings": ops,
            "group": meta["group"],
            "label": meta["label"],
            "removable": meta["removable"],
        })

    # 3. Extract 24 indoor panorama sweeps
    with open(f"{BASE_DIR}/api/mp/models/graph_GetShowcaseSweeps.json") as f:
        sweeps_raw = json.load(f)["data"]["model"]["locations"]

    pano_dir = "/home/antigravity/Matterport-/assets/panos"
    pano_files = os.listdir(pano_dir)

    room_for_sweep = {
        1: "Front Porch / Entry",
        2: "Living Room (Entry)",
        3: "Dining Room / Hallway",
        4: "Dining Room",
        5: "Dining Room (South Window)",
        6: "Kitchen (Peninsula)",
        7: "Kitchen (Sink & Window)",
        8: "Kitchen (Back Door)",
        9: "Back Steps / Laundry Entry",
        10: "Laundry Room (South)",
        11: "Laundry Room (East)",
        12: "Laundry Room (Washer)",
        15: "Hallway (East)",
        16: "Bedroom 1 (12'1\" × 10'1\")",
        17: "Hallway (Center)",
        18: "Bathroom (6'10\" × 10'1\")",
        19: "Hallway (West)",
        20: "Bedroom 2 (8'10\" × 13'6\")",
        21: "Bedroom 2 (Window)",
        22: "Living Room (East)",
        23: "Living Room (Center)",
        24: "Living Room (Picture Window)",
        25: "Office (13'10\" × 13' Entry)",
        26: "Office (North Corner)",
    }

    sweeps = []
    for s in sweeps_raw:
        idx = s.get("index")
        if idx in room_for_sweep:
            pos = s["position"]
            rot = s["pano"]["rotation"]
            prefix = f"sweep_{idx:02d}_"
            matching = [fn for fn in pano_files if fn.startswith(prefix) and fn.endswith("_face0.jpg")]
            base_prefix = matching[0][:-10] if matching else None
            if base_prefix:
                sweeps.append({
                    "index": idx,
                    "id": s["id"],
                    "room": room_for_sweep[idx],
                    "x": round(pos["x"], 3),
                    "y": round(pos["y"], 3),
                    "z": round(pos["z"], 3),
                    "panoZ": round(s["pano"]["position"]["z"], 3),
                    "rotation": {k: round(rot[k], 4) for k in ("x", "y", "z", "w")},
                    "filePrefix": base_prefix,
                })
    sweeps.sort(key=lambda x: x["index"])

    # 4. Exact architectural room definitions matching image.png & Matterport coordinates
    rooms = [
        {
            "id": "living_room",
            "name": "Living Room",
            "dimensions": "22'7\" × 12'11\"",
            "sqft": 292,
            "xMin": 3.19, "xMax": 7.43,
            "yMin": 1.84, "yMax": 8.55,
            "floorZ": -1.14, "ceilZ": 2.82,
            "vaulted": True,
            "sweepIndex": 23,
            "photo": "kitchen_dining.jpg",
            "features": "Vaulted cedar plank ceiling, south 3-panel orchard window, clerestory gable glass, oak mosaic parquet floor, diagonal dark-brick wood-burning fireplace.",
        },
        {
            "id": "office",
            "name": "Office / Den",
            "dimensions": "13'10\" × 13'0\"",
            "sqft": 180,
            "xMin": 7.43, "xMax": 11.61,
            "yMin": 3.37, "yMax": 8.55,
            "floorZ": -0.96, "ceilZ": 2.82,
            "vaulted": True,
            "sweepIndex": 25,
            "photo": "dollhouse_overview.jpg",
            "features": "Step-up carpeted floor (+18 cm), mid-century wood pony wall overlooking Living Room, vaulted cedar ceiling, north & west windows.",
        },
        {
            "id": "dining_room",
            "name": "Dining Room",
            "dimensions": "10'4\" × 10'6\"",
            "sqft": 109,
            "xMin": 3.16, "xMax": 6.71,
            "yMin": -3.00, "yMax": 1.84,
            "floorZ": -1.14, "ceilZ": 1.30,
            "vaulted": False,
            "sweepIndex": 4,
            "photo": "kitchen_dining.jpg",
            "features": "Oak mosaic parquet floor, south diamond-leaded casement window, brass chandelier, turquoise booth bench backing onto Kitchen peninsula.",
        },
        {
            "id": "kitchen",
            "name": "Kitchen",
            "dimensions": "9'5\" × 19'7\"",
            "sqft": 184,
            "xMin": 2.48, "xMax": 8.56,
            "yMin": -6.01, "yMax": -2.96,
            "floorZ": -1.14, "ceilZ": 1.30,
            "vaulted": False,
            "sweepIndex": 8,
            "photo": "kitchen_main.jpg",
            "features": "1963 birch cabinets, turquoise laminate counters & backsplash, U-peninsula with gas cooktop, chain-hung display cabinet, charcoal-brick wall oven column.",
        },
        {
            "id": "hallway",
            "name": "Hallway & Central Closet",
            "dimensions": "10'3\" × 6'9\"",
            "sqft": 70,
            "xMin": 6.70, "xMax": 8.56,
            "yMin": -3.18, "yMax": 0.38,
            "floorZ": -1.14, "ceilZ": 1.30,
            "vaulted": False,
            "sweepIndex": 17,
            "photo": "bedroom_west_2.jpg",
            "features": "Birch wood paneling, central enclosed closet block (x: 6.70–7.48, y: -2.96 to -0.68) separating Hallway from Dining Room.",
        },
        {
            "id": "bedroom_2",
            "name": "Bedroom 2 (West)",
            "dimensions": "8'10\" × 13'6\"",
            "sqft": 119,
            "xMin": 7.44, "xMax": 11.64,
            "yMin": 0.37, "yMax": 3.37,
            "floorZ": -1.14, "ceilZ": 1.30,
            "vaulted": False,
            "sweepIndex": 20,
            "photo": "bedroom_west_1.jpg",
            "features": "Warm walnut vertical wood paneling, beige carpet, north triple window, louvered bi-fold closet on east wall.",
        },
        {
            "id": "bathroom",
            "name": "Bathroom",
            "dimensions": "6'10\" × 10'1\"",
            "sqft": 69,
            "xMin": 8.54, "xMax": 11.75,
            "yMin": -1.93, "yMax": 0.08,
            "floorZ": -1.14, "ceilZ": 1.30,
            "vaulted": False,
            "sweepIndex": 18,
            "photo": "bedroom_west_2.jpg",
            "features": "Speckled mid-century mosaic tile walls & floor, black vanity with round turquoise sink, triple mirror medicine cabinet, tub/shower alcove, linen closet.",
        },
        {
            "id": "bedroom_1",
            "name": "Bedroom 1 (East)",
            "dimensions": "12'1\" × 10'1\"",
            "sqft": 122,
            "xMin": 8.55, "xMax": 11.78,
            "yMin": -5.99, "yMax": -1.92,
            "floorZ": -1.14, "ceilZ": 1.30,
            "vaulted": False,
            "sweepIndex": 16,
            "photo": "bedroom_east.jpg",
            "features": "Birch wood wall paneling, beige carpet, wide north window, bi-fold louvered wood closet on east wall.",
        },
        {
            "id": "laundry",
            "name": "Laundry & Storage",
            "dimensions": "11'7\" × 10'0\" + 5' × 5'10\"",
            "sqft": 145,
            "xMin": 8.57, "xMax": 11.81,
            "yMin": -9.81, "yMax": -6.00,
            "floorZ": -1.09, "ceilZ": 1.30,
            "vaulted": False,
            "sweepIndex": 12,
            "photo": "laundry_room.jpg",
            "features": "Grey-oak plank floor, oak upper cabinets, Maytag washer/dryer area, enclosed 5'×5'10\" storage room, exterior door to carport steps.",
        },
        {
            "id": "carport",
            "name": "Covered Carport",
            "dimensions": "20'0\" × 12'6\"",
            "sqft": 250,
            "xMin": 2.49, "xMax": 8.57,
            "yMin": -9.81, "yMax": -6.01,
            "floorZ": -1.72, "ceilZ": 1.30,
            "vaulted": False,
            "sweepIndex": 13,
            "photo": "exterior_carport.jpg",
            "features": "Covered concrete carport on east side of house with curved concrete steps up to Kitchen & Laundry entries.",
        },
    ]

    payload = {
        "modelId": "rfwtuskak8Q",
        "title": "1346 Russell Road, Gibsons, BC V0N 1V2",
        "MLS": "R3119342",
        "lotSize": "10.82 Acres (471,754 sq ft)",
        "houseSqft": 1279,
        "yearBuilt": 1963,
        "meshChunks": mesh_chunks,
        "walls": walls,
        "sweeps": sweeps,
        "rooms": rooms,
    }

    js_str = "window.HOUSE_DATA = " + json.dumps(payload, separators=(",", ":")) + ";\n"
    with open(OUT_JS, "w", encoding="utf-8") as f:
        f.write(js_str)
    print(f"Wrote {OUT_JS} ({len(js_str):,} bytes)")


if __name__ == "__main__":
    main()
