import re
import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
from streamlit_folium import st_folium
from shapely.geometry import Point
from shapely import wkt

# ============================================
# PAGE CONFIG
# ============================================
st.set_page_config(
    page_title="Oshana FloodX",
    layout="wide"
)

# ============================================
# KNOWN OSHANA CONSTITUENCY NAMES
# ============================================
KNOWN_CONSTITUENCIES = [
    "Okaku",
    "Okatana",
    "Ompundja",
    "Ondangwa Rural",
    "Ondangwa Urban",
    "Ongwediva",
    "Oshakati East",
    "Oshakati West",
    "Uukwiyu",
    "Uuvudhiya"
]

# ============================================
# LOAD KML SAFELY AND FAST
# ============================================
@st.cache_data(show_spinner=False)
def load_constituencies():
    data = gpd.read_file("oshana_constituencies.kml", driver="KML")

    if data.empty:
        return data

    data = data.to_crs(epsg=4326)
    data = data.reset_index(drop=True)
    data["_poly_id"] = data.index

    data["geometry"] = data.geometry.simplify(
        0.0012,
        preserve_topology=True
    )

    return data


try:
    gdf = load_constituencies()

    if gdf.empty:
        st.error("The KML file loaded, but it has no data.")
        st.stop()

except Exception as e:
    st.error("Failed to load oshana_constituencies.kml")
    st.write(e)
    st.stop()

# ============================================
# LOAD ROADS CSV SAFELY AND FAST
# ============================================
@st.cache_data(show_spinner=False)
def load_roads():
    try:
        roads_df = pd.read_csv("oshana_roads_utm33s.csv")
        roads_df.columns = roads_df.columns.str.strip()

        if "geometry_wkt" not in roads_df.columns:
            return None

        roads_df["geometry"] = roads_df["geometry_wkt"].apply(
            lambda x: wkt.loads(str(x))
            if pd.notna(x) and str(x).strip() not in ["", "None", "nan", "NaN"]
            else None
        )

        roads_data = gpd.GeoDataFrame(
            roads_df,
            geometry="geometry",
            crs="EPSG:32733"
        )

        roads_data = roads_data.dropna(subset=["geometry"])
        roads_data = roads_data[~roads_data.geometry.is_empty]

        if roads_data.empty:
            return None

        roads_data = roads_data.to_crs(epsg=4326)

        roads_data["geometry"] = roads_data.geometry.simplify(
            0.0015,
            preserve_topology=True
        )

        roads_data = roads_data[~roads_data.geometry.is_empty].reset_index(drop=True)

        return roads_data

    except Exception:
        return None


roads_gdf = load_roads()

# ============================================
# EXTRACT REAL CONSTITUENCY NAMES SAFELY
# ============================================
def clean_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def find_name_from_row(row):
    combined_text = " ".join(
        clean_text(row[col])
        for col in gdf.columns
        if col != "geometry"
    )

    combined_text_lower = combined_text.lower()

    for cname in KNOWN_CONSTITUENCIES:
        if cname.lower() in combined_text_lower:
            return cname

    if "uvudhiya" in combined_text_lower or "uuvudhiya" in combined_text_lower:
        return "Uuvudhiya"

    if "ongwediva" in combined_text_lower:
        return "Ongwediva"

    if "oshakati east" in combined_text_lower:
        return "Oshakati East"

    if "oshakati west" in combined_text_lower:
        return "Oshakati West"

    if "ondangwa urban" in combined_text_lower:
        return "Ondangwa Urban"

    if "ondangwa rural" in combined_text_lower:
        return "Ondangwa Rural"

    return None


gdf["Constituency_Name"] = gdf.apply(find_name_from_row, axis=1)

if gdf["Constituency_Name"].isna().sum() > 0:
    gdf["Constituency_Name"] = gdf.apply(
        lambda row: row["Constituency_Name"]
        if pd.notna(row["Constituency_Name"])
        else f"Polygon {int(row['_poly_id']) + 1}",
        axis=1
    )

name_field = "Constituency_Name"

gdf["dropdown_label"] = gdf.apply(
    lambda row: f"{row[name_field]}",
    axis=1
)

seen = {}
labels = []

for idx, row in gdf.iterrows():
    label = str(row["dropdown_label"])

    if label in seen:
        seen[label] += 1
        label = f"{label} ({seen[label]})"
    else:
        seen[label] = 1

    labels.append(label)

gdf["dropdown_label"] = labels

dropdown_to_poly_id = dict(zip(gdf["dropdown_label"], gdf["_poly_id"]))
poly_id_to_dropdown = dict(zip(gdf["_poly_id"], gdf["dropdown_label"]))

constituencies = gdf["dropdown_label"].tolist()

# ============================================
# SESSION STATE
# ============================================
if "page" not in st.session_state:
    st.session_state.page = "home"

if "hazard" not in st.session_state:
    st.session_state.hazard = "River Flood"

if "selected_poly_id" not in st.session_state:
    st.session_state.selected_poly_id = None

if "show_safe_roads" not in st.session_state:
    st.session_state.show_safe_roads = True

if "show_risk_roads" not in st.session_state:
    st.session_state.show_risk_roads = True

# ============================================
# COLORS
# ============================================
colors = {
    "High": "#d81b60",
    "Medium": "#f46d43",
    "Low": "#fdae61",
    "Very Low": "#fee08b"
}

hazard_levels = [
    "High",
    "Medium",
    "Low",
    "High",
    "Medium",
    "Very Low",
    "Low",
    "Medium",
    "High",
    "Low"
]

hazard_text = {
    "River Flood": "River flood hazard shows constituencies that may be affected by flooding along river channels and drainage areas.",
    "Urban Flood": "Urban flood hazard highlights built-up areas that may experience surface flooding after heavy rainfall.",
    "Rural Flood": "Rural flood hazard shows rural constituencies that may be exposed to flood risk and drainage problems.",
    "Water Body": "Water body hazard highlights constituencies closer to water bodies or flood-prone drainage zones."
}
# ====================================
# HAZARD LEVELS CHANGE WITH ICONS
# ====================================
hazard_level_by_type = {

    "River Flood": [
        "High",
        "High",
        "Medium",
        "High",
        "Medium",
        "Very Low",
        "Low",
        "Medium",
        "High",
        "Low"
    ],

    "Urban Flood": [
        "Medium",
        "High",
        "High",
        "Low",
        "High",
        "Very Low",
        "Medium",
        "High",
        "Low",
        "Medium"
    ],

    "Rural Flood": [
        "High",
        "Medium",
        "Low",
        "High",
        "Medium",
        "Very Low",
        "Low",
        "Medium",
        "High",
        "Low"
    ],

    "Water Body": [
        "Low",
        "Medium",
        "High",
        "Medium",
        "Low",
        "Very Low",
        "High",
        "Medium",
        "Low",
        "High"
    ]
}

# ====================================
# GET CURRENT HAZARD LEVELS
# ====================================
current_levels = hazard_level_by_type.get(
    st.session_state.hazard,
    hazard_level_by_type["River Flood"]
)

# ============================================
# PREPARE ROAD STATUS ONCE FOR SPEED
# ============================================
@st.cache_data(show_spinner=False)
def prepare_roads_with_status(_roads_data, _constituencies_data, hazard_name):
    if _roads_data is None:
        return None

    roads_out = _roads_data.copy()
    constituencies_data = _constituencies_data.copy()

    statuses = []
    colors_out = []

    current_levels_local = hazard_level_by_type.get(
        hazard_name,
        hazard_level_by_type["River Flood"]
    )

    hazard_lookup = {
        int(row["_poly_id"]): current_levels_local[idx % len(current_levels_local)]
        for idx, row in constituencies_data.iterrows()
    }

    for road_idx, road in roads_out.iterrows():
        road_geom = road.geometry
        road_status = "Safe Road"
        road_color = "green"

        if road_geom is None or road_geom.is_empty:
            statuses.append(road_status)
            colors_out.append(road_color)
            continue

        for idx, area in constituencies_data.iterrows():
            area_geom = area.geometry

            if area_geom is None or area_geom.is_empty:
                continue

            level = hazard_lookup.get(int(area["_poly_id"]), "Low")

            try:
                if road_geom.intersects(area_geom):
                    if level in ["High", "Medium"]:
                        road_status = "Risk Road"
                        road_color = "red"
                        break
            except Exception:
                continue

        statuses.append(road_status)
        colors_out.append(road_color)

    roads_out["road_status"] = statuses
    roads_out["road_color"] = colors_out

    return roads_out


roads_gdf = prepare_roads_with_status(
    roads_gdf,
    gdf,
    st.session_state.hazard
)

# ============================================
# HOME PAGE
# ============================================
if st.session_state.page == "home":

    st.markdown("""
    <style>
    .stApp {
        background: linear-gradient(to right,#243743,#607d8b);
    }

    .home-box {
        background:white;
        width:650px;
        padding:50px;
        border-radius:18px;
        text-align:center;
        margin:auto;
        margin-top:150px;
        box-shadow:0 0 20px rgba(0,0,0,0.3);
    }

    div.stButton > button {
        background:#e4003a;
        color:white;
        border:none;
        padding:14px 28px;
        border-radius:8px;
        font-weight:bold;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="home-box">
        <h1>Oshana FloodX</h1>
        <h2>Welcome to the Hazard Assessment App</h2>
        <p>Choose country: Namibia</p>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3 = st.columns([2, 1, 2])

    with c2:
        if st.button("Open Hazard Map", key="open_hazard_map"):
            st.session_state.page = "map"
            st.rerun()

# ============================================
# MAP PAGE
# ============================================
else:

    st.markdown("""
    <style>
    .stApp {
        background:white;
    }

    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 0.3rem !important;
        max-width: 100% !important;
    }

    div[data-testid="column"] {
        overflow: visible !important;
    }

    div.stButton > button {
        background:#333;
        color:white;
        border:none;
        padding:8px 14px;
        border-radius:8px;
        font-weight:bold;
    }

    div.stButton > button:disabled {
        background:#e4003a !important;
        color:white !important;
        opacity:1 !important;
        border:2px solid #e4003a !important;
    }

    .icon-box {
        text-align:center;
        font-weight:bold;
        font-size:11px;
        width:100%;
        margin-top:8px;
        margin-bottom:-5px;
    }

    .circle {
        width:56px;
        height:56px;
        border-radius:50%;
        background:white;
        box-shadow:0 0 8px rgba(0,0,0,0.25);
        display:flex;
        align-items:center;
        justify-content:center;
        font-size:26px;
        margin:auto;
        border:4px solid #e4003a;
    }

    .active-circle {
        background:#e4003a;
        color:white;
    }

    .title-row {
        display:flex;
        justify-content:space-between;
        align-items:center;
        border-bottom:2px solid #e4003a;
    }

    .title-row h1 {
        font-size:36px;
        font-weight:400;
        margin-bottom:0px;
    }

    .hazard-level {
        color:#e4003a;
        font-style:italic;
        font-weight:bold;
        font-size:16px;
    }

    .recommendation {
        border-left:6px solid #e4003a;
        padding-left:15px;
        font-size:16px;
        line-height:1.35;
    }

    .selected-box {
        background:#f5f5f5;
        padding:12px;
        border-radius:8px;
        border:1px solid #ddd;
        font-size:15px;
        margin-top:15px;
    }

    iframe {
        width:100% !important;
        border-radius:12px !important;
    }
    </style>
    """, unsafe_allow_html=True)

    top_prev, top_icons = st.columns([0.6, 5.4])

    with top_prev:
        if st.button("← Previous page", key="prev_page_btn"):
            st.session_state.page = "home"
            st.rerun()

    with top_icons:
        i1, i2, i3, i4 = st.columns(
            [1, 1, 1, 1],
            gap="small"
        )

        with i1:
            active = "active-circle" if st.session_state.hazard == "River Flood" else ""
            st.markdown(
                f"<div class='icon-box'><div class='circle {active}'>🌊</div>River Flood</div>",
                unsafe_allow_html=True
            )
            if st.button(
                "River Flood",
                key="river_btn",
                disabled=st.session_state.hazard == "River Flood"
            ):
                st.session_state.hazard = "River Flood"
                st.rerun()

        with i2:
            active = "active-circle" if st.session_state.hazard == "Urban Flood" else ""
            st.markdown(
                f"<div class='icon-box'><div class='circle {active}'>🏙️</div>Urban Flood</div>",
                unsafe_allow_html=True
            )
            if st.button(
                "Urban Flood",
                key="urban_btn",
                disabled=st.session_state.hazard == "Urban Flood"
            ):
                st.session_state.hazard = "Urban Flood"
                st.rerun()

        with i3:
            active = "active-circle" if st.session_state.hazard == "Rural Flood" else ""
            st.markdown(
                f"<div class='icon-box'><div class='circle {active}'>⛰️</div>Rural Flood</div>",
                unsafe_allow_html=True
            )
            if st.button(
                "Rural Flood",
                key="rural_btn",
                disabled=st.session_state.hazard == "Rural Flood"
            ):
                st.session_state.hazard = "Rural Flood"
                st.rerun()

        with i4:
            active = "active-circle" if st.session_state.hazard == "Water Body" else ""
            st.markdown(
                f"<div class='icon-box'><div class='circle {active}'>💧</div>Water Body</div>",
                unsafe_allow_html=True
            )
            if st.button(
                "Water Body",
                key="water_btn",
                disabled=st.session_state.hazard == "Water Body"
            ):
                st.session_state.hazard = "Water Body"
                st.rerun()

    st.markdown("### Namibia › Oshana")

    selected_index = 0

    if st.session_state.selected_poly_id is not None:
        selected_label_current = poly_id_to_dropdown.get(st.session_state.selected_poly_id)

        if selected_label_current in constituencies:
            selected_index = constituencies.index(selected_label_current) + 1

    selected_label = st.selectbox(
        "Click/select constituency to zoom",
        ["Show all constituencies"] + constituencies,
        index=selected_index
    )

    if selected_label != "Show all constituencies":
        st.session_state.selected_poly_id = dropdown_to_poly_id[selected_label]
    else:
        st.session_state.selected_poly_id = None

    selected_name = None

    if st.session_state.selected_poly_id is not None:
        selected_rows_temp = gdf[gdf["_poly_id"] == st.session_state.selected_poly_id]

        if not selected_rows_temp.empty:
            selected_name = selected_rows_temp.iloc[0][name_field]

    # ============================================
    # ROAD FILTER BUTTONS
    # ============================================
    st.markdown("#### Road Display")

    road_btn1, road_btn2, road_btn3 = st.columns([1, 1, 5])

    with road_btn1:
        safe_text = "🟢 Safe Roads ON" if st.session_state.show_safe_roads else "⚪ Safe Roads OFF"

        if st.button(safe_text, key="safe_roads_btn"):
            st.session_state.show_safe_roads = not st.session_state.show_safe_roads
            st.rerun()

    with road_btn2:
        risk_text = "🔴 Risk Roads ON" if st.session_state.show_risk_roads else "⚪ Risk Roads OFF"

        if st.button(risk_text, key="risk_roads_btn"):
            st.session_state.show_risk_roads = not st.session_state.show_risk_roads
            st.rerun()

    with road_btn3:
        if st.button("Show All Roads", key="show_all_roads_btn"):
            st.session_state.show_safe_roads = True
            st.session_state.show_risk_roads = True
            st.rerun()

    left, right = st.columns([0.95, 2.05], gap="medium")

    with left:
        st.markdown(f"""
        <div class="title-row">
            <h1>{st.session_state.hazard}</h1>
            <p class="hazard-level">Hazard level: High</p>
        </div>
        """, unsafe_allow_html=True)

        st.write(hazard_text[st.session_state.hazard])

        st.markdown("## Recommendations")

        st.markdown("""
        <div class="recommendation">
        - Use the map to identify constituencies with higher hazard levels.<br>
        - Planning decisions should consider flood exposure, settlement location, drainage and climate change impacts.
        </div>
        """, unsafe_allow_html=True)

        if roads_gdf is None:
            st.warning("Road CSV not loaded. Make sure oshana_roads_utm33s.csv is in the same folder and has a geometry_wkt column.")

        if selected_name:
            st.markdown(f"""
            <div class="selected-box">
            Selected constituency: <b>{selected_name}</b>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="selected-box">
            Select a constituency from the dropdown or click directly on the map.
            </div>
            """, unsafe_allow_html=True)

        if selected_name:
            if st.button("Show Full Oshana Again", key="show_full_oshana_btn"):
                st.session_state.selected_poly_id = None
                st.rerun()

    with right:
        m = folium.Map(
            location=[-17.95, 15.85],
            zoom_start=9,
            tiles="CartoDB positron",
            prefer_canvas=True
        )

        # ====================================
        # DRAW CONSTITUENCIES
        # Hazard colors change when the hazard icons are clicked
        # ====================================
        current_levels = hazard_level_by_type.get(
            st.session_state.hazard,
            hazard_level_by_type["River Flood"]
        )

        for idx, row in gdf.iterrows():

            level = current_levels[idx % len(current_levels)]
            name = str(row[name_field])
            poly_id = int(row["_poly_id"])

            if st.session_state.selected_poly_id is not None and poly_id != st.session_state.selected_poly_id:
                continue

            folium.GeoJson(
                row.geometry,
                zoom_on_click=True,
                style_function=lambda feature, level=level: {
                    "fillColor": colors[level],
                    "color": "black",
                    "weight": 4,
                    "fillOpacity": 0.70
                },
                highlight_function=lambda feature: {
                    "weight": 5,
                    "color": "yellow",
                    "fillOpacity": 0.82
                },
                tooltip=f"{name} | {st.session_state.hazard}: {level}",
                popup=f"<b>{name}</b><br>{st.session_state.hazard}: <b>{level}</b>"
            ).add_to(m)

        # ====================================
        # DRAW SAFE AND RISK ROADS
        # ====================================
        if roads_gdf is not None:

            roads_to_draw = roads_gdf.copy()

            if st.session_state.selected_poly_id is not None:
                selected_area = gdf[gdf["_poly_id"] == st.session_state.selected_poly_id]

                if not selected_area.empty:
                    selected_geom = selected_area.geometry.iloc[0]
                    roads_to_draw = roads_to_draw[roads_to_draw.geometry.intersects(selected_geom)]

            if not st.session_state.show_safe_roads:
                roads_to_draw = roads_to_draw[roads_to_draw["road_status"] != "Safe Road"]

            if not st.session_state.show_risk_roads:
                roads_to_draw = roads_to_draw[roads_to_draw["road_status"] != "Risk Road"]

            for road_status, road_color in [("Risk Road", "red"), ("Safe Road", "green")]:
                group = roads_to_draw[roads_to_draw["road_status"] == road_status]

                if group.empty:
                    continue

                folium.GeoJson(
                    group[["geometry", "road_status"]].to_json(),
                    name=road_status,
                    style_function=lambda feature, road_color=road_color: {
                        "color": road_color,
                        "weight": 1.7,
                        "opacity": 0.72
                    },
                    tooltip=folium.GeoJsonTooltip(
                        fields=["road_status"],
                        aliases=["Road Status:"],
                        sticky=True
                    )
                ).add_to(m)

        # ====================================
        # ZOOM TO SELECTED CONSTITUENCY
        # ====================================
        try:
            if st.session_state.selected_poly_id is not None:
                selected_rows = gdf[gdf["_poly_id"] == st.session_state.selected_poly_id]

                if not selected_rows.empty:
                    selected_geom = selected_rows.geometry.iloc[0]
                    minx, miny, maxx, maxy = selected_geom.bounds
                    m.fit_bounds([[miny, minx], [maxy, maxx]], padding=(18, 18))
            else:
                minx, miny, maxx, maxy = gdf.total_bounds
                m.fit_bounds([[miny, minx], [maxy, maxx]], padding=(18, 18))

        except Exception:
            pass

        # ====================================
        # LEGEND
        # ====================================
        legend_html = """
        <div style="
            position: fixed;
            bottom: 35px;
            left: 35px;
            z-index:9999;
            background:white;
            padding:10px;
            border-radius:10px;
            display:grid;
            grid-template-columns:105px 105px;
            gap:8px;
            box-shadow:0 0 10px rgba(0,0,0,0.25);
            font-size:13px;
        ">

        <div><span style="background:#d81b60;width:20px;height:20px;display:inline-block;margin-right:8px;"></span>High</div>
        <div><span style="background:#f46d43;width:20px;height:20px;display:inline-block;margin-right:8px;"></span>Medium</div>
        <div><span style="background:#fdae61;width:20px;height:20px;display:inline-block;margin-right:8px;"></span>Low</div>
        <div><span style="background:#fee08b;width:20px;height:20px;display:inline-block;margin-right:8px;"></span>Very Low</div>
        <div><span style="background:green;width:26px;height:5px;display:inline-block;margin-right:8px;"></span>Safe Road</div>
        <div><span style="background:red;width:26px;height:5px;display:inline-block;margin-right:8px;"></span>Risk Road</div>

        </div>
        """

        m.get_root().html.add_child(folium.Element(legend_html))

        map_data = st_folium(
            m,
            width=None,
            height=430,
            returned_objects=["last_clicked"],
            use_container_width=True,
            key=f"oshana_map_{st.session_state.hazard}_{st.session_state.selected_poly_id}_{st.session_state.show_safe_roads}_{st.session_state.show_risk_roads}"
        )

        # ====================================
        # CLICK SELECTION LOGIC
        # ====================================
        if map_data and map_data.get("last_clicked") is not None:

            lat = map_data["last_clicked"]["lat"]
            lon = map_data["last_clicked"]["lng"]
            clicked_point = Point(lon, lat)

            for idx, row in gdf.iterrows():
                try:
                    if row.geometry.contains(clicked_point):
                        clicked_poly_id = int(row["_poly_id"])

                        if st.session_state.selected_poly_id != clicked_poly_id:
                            st.session_state.selected_poly_id = clicked_poly_id
                            st.rerun()

                except Exception:
                    pass
