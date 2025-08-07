import streamlit as st
import pandas as pd
import pydeck as pdk
import geopandas as gpd
from shapely.geometry import Point
from opencage.geocoder import OpenCageGeocode
import os

# ─── CONFIG ──────────────────────────────────────────────────────────────
os.environ["MAPBOX_API_KEY"] = "pk.eyJ1IjoicnNpZGRpcTIiLCJhIjoiY21jbjcwNWtkMHV5bzJpb2pnM3QxaDFtMyJ9.6T6i_QFuKQatpGaCFUvCKg"  # replace with your token

ODM_CSV = "ODM_CAFN.csv"
TRACTS_SHP = "cb_2023_37_tract_500k.shp"
OPENCAGE_API_KEY = "f53bdda785074d5499b7a4d29d5acd1f"  # replace with your key
geocoder = OpenCageGeocode(OPENCAGE_API_KEY)

st.set_page_config(page_title="Nearby Food Pantries", layout="wide")
st.title("Find Nearby Food Pantries")

# ─── USER ADDRESS ────────────────────────────────────────────────────────
user_address = st.text_input("Enter your address (e.g., 123 Main St, Raleigh, NC):")

if user_address:
    try:
        results = geocoder.geocode(user_address)
        if results:
            user_lat = results[0]["geometry"]["lat"]
            user_lon = results[0]["geometry"]["lng"]
            st.success(f"Geocoded location: {user_lat:.5f}, {user_lon:.5f}")
        else:
            st.error("Could not geocode your address.")
            st.stop()
    except Exception as e:
        st.error(f"Geocoding error: {e}")
        st.stop()

    # ─── LOAD DATA ───────────────────────────────────────────────────────
    odm_df = pd.read_csv(ODM_CSV)
    odm_df.columns = odm_df.columns.str.strip().str.lower()
    odm_df["geoid"] = odm_df["geoid"].astype(int)

    tracts_gdf = gpd.read_file(TRACTS_SHP).to_crs(epsg=4326)
    if tracts_gdf["GEOID"].dtype == object:
        tracts_gdf["GEOID"] = tracts_gdf["GEOID"].astype(int)

    # ─── MATCH GEOID ─────────────────────────────────────────────────────
    user_point = Point(user_lon, user_lat)
    matched_tract = tracts_gdf[tracts_gdf.contains(user_point)]

    if not matched_tract.empty:
        user_geoid = matched_tract.iloc[0]["GEOID"]
        st.success(f"Matched your location to GEOID {user_geoid}")
    else:
        st.error("Could not match your location to a census tract.")
        st.stop()

    # ─── FIND NEARBY AGENCIES ────────────────────────────────────────────
    agencies_nearby = odm_df[
        (odm_df["geoid"] == user_geoid) &
        (odm_df["total_traveltime"] <= 20)
    ]

    if agencies_nearby.empty:
        st.warning("No agencies directly linked to your tract. Showing agencies within 60-minute travel time.")
        agencies_nearby = odm_df[odm_df["total_traveltime"] <= 60]

    # 🚨 FILTER SECTION ────────────────────────────────────────────────────
    df = agencies_nearby.copy()
    show_choice_only = st.checkbox("Show only Choice Pantries", value=False)

    st.markdown("### Select Categories")
    filter_1_vals = sorted(df["filter_1"].dropna().unique())
    selected_filter_1 = st.multiselect("", filter_1_vals, label_visibility="collapsed", key="filter_1_multi")

    for val in filter_1_vals:
        color = "#1f77b4"
        is_selected = val in selected_filter_1
        st.markdown(
            f"<div style='padding: 6px; background-color:{color if is_selected else '#e0e0e0'}; "
            f"color:white; border-radius:5px; margin-bottom:5px'>{val}</div>",
            unsafe_allow_html=True
        )

    filtered_df = df[df["filter_1"].isin(selected_filter_1)] if selected_filter_1 else df.copy()

    if not filtered_df.empty:
        st.markdown("### Select Subcategories")
        filter_2_vals = sorted(filtered_df["filter_2"].dropna().unique())
        selected_filter_2 = st.multiselect("", filter_2_vals, label_visibility="collapsed", key="filter_2_multi")

        for val in filter_2_vals:
            color = "#ff7f0e"
            is_selected = val in selected_filter_2
            st.markdown(
                f"<div style='padding: 6px; background-color:{color if is_selected else '#e0e0e0'}; "
                f"color:white; border-radius:5px; margin-bottom:5px'>{val}</div>",
                unsafe_allow_html=True
            )

        if selected_filter_2:
            filtered_df = filtered_df[filtered_df["filter_2"].isin(selected_filter_2)]

    if show_choice_only:
        filtered_df = filtered_df[filtered_df["choice"] == 1]

    # ─── DISPLAY RESULTS ─────────────────────────────────────────────────
    if not filtered_df.empty:
        filtered_df = filtered_df.copy()
        filtered_df["total_traveltime"] = filtered_df["total_traveltime"].round(2)
        filtered_df["total_miles"] = filtered_df["total_miles"].round(2)

        st.success(f"{len(filtered_df)} pantries match your filters.")
        display_cols = ["agency name", "address", "operating hours", "contact", "total_traveltime", "total_miles"]
        st.dataframe(filtered_df[display_cols].drop_duplicates().sort_values("total_traveltime"))

        # ─── MAP DISPLAY ────────────────────────────────────────────────
        user_df = pd.DataFrame({
            "name": ["Your Location"],
            "latitude": [user_lat],
            "longitude": [user_lon],
            "color_r": [0], "color_g": [0], "color_b": [255],
            "tooltip": ["Your Location"]
        })

        agency_map_df = filtered_df.copy()
        agency_map_df["color_r"] = 255
        agency_map_df["color_g"] = 0
        agency_map_df["color_b"] = 0
        agency_map_df["tooltip"] = (
            "Agency: " + agency_map_df["agency name"] +
            "<br>Travel Time (min): " + agency_map_df["total_traveltime"].astype(str) +
            "<br>Distance (miles): " + agency_map_df["total_miles"].astype(str)
        )

        combined_df = pd.concat([user_df, agency_map_df], ignore_index=True)

        layer = pdk.Layer(
            "ScatterplotLayer",
            combined_df,
            get_position='[longitude, latitude]',
            get_color='[color_r, color_g, color_b]',
            get_radius=250,
            pickable=True,
        )

        view_state = pdk.ViewState(
            longitude=user_lon, latitude=user_lat, zoom=10, pitch=0
        )

        deck = pdk.Deck(
            map_style='mapbox://styles/mapbox/light-v9',
            initial_view_state=view_state,
            layers=[layer],
            tooltip={"html": "{tooltip}", "style": {"color": "white"}}
        )

        st.pydeck_chart(deck)
    else:
        st.warning("No agencies found matching your filters.")
