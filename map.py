import streamlit as st
import pandas as pd
import pydeck as pdk
import geopandas as gpd
from shapely.geometry import Point
from datetime import datetime, time
from opencage.geocoder import OpenCageGeocode
from dateutil import parser
import os

# ─── CONFIG ──────────────────────────────────────────────────────────────

# Set your Mapbox token as environment variable
os.environ["MAPBOX_API_KEY"] = "pk.eyJ1IjoicnNpZGRpcTIiLCJhIjoiY21jbjcwNWtkMHV5bzJpb2pnM3QxaDFtMyJ9.6T6i_QFuKQatpGaCFUvCKg"

ODM_CSV = "ODM_CAFN.csv"
TRACTS_SHP = "cb_2023_37_tract_500k.shp"
OPENCAGE_API_KEY = "f53bdda785074d5499b7a4d29d5acd1f"
geocoder = OpenCageGeocode(OPENCAGE_API_KEY)

# ─── STREAMLIT ───────────────────────────────────────────────────────────

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
      
    # 🚨 CASCADING FILTER UI SECTION
    # ===============================
    
    st.subheader("Filter Options")
    
    # 1️⃣ Unique values from filter_1
    filter_1_values = sorted(agencies_nearby["filter_1"].dropna().unique())
    selected_filter_1 = None
    selected_filter_2 = None
    
    # Display filter_1 as buttons (horizontal or vertical)
    for val in filter_1_values:
        if st.button(f"Filter 1: {val}"):
            selected_filter_1 = val
            st.session_state['selected_filter_1'] = val
    
    # Retain session state on rerun
    selected_filter_1 = st.session_state.get('selected_filter_1', None)
    
    # 2️⃣ Show second layer of buttons from filter_2
    if selected_filter_1:
        filtered_by_1 = agencies_nearby[agencies_nearby["filter_1"] == selected_filter_1]
        filter_2_values = sorted(filtered_by_1["filter_2"].dropna().unique())
    
        for val in filter_2_values:
            if st.button(f"Filter 2: {val}"):
                selected_filter_2 = val
                st.session_state['selected_filter_2'] = val
    
        selected_filter_2 = st.session_state.get('selected_filter_2', None)
    
        # Update agencies_nearby based on both filters
        agencies_nearby = agencies_nearby[agencies_nearby["filter_1"] == selected_filter_1]
    
        if selected_filter_2:
            agencies_nearby = agencies_nearby[agencies_nearby["filter_2"] == selected_filter_2]
    
    # 3️⃣ Choice Pantry filter (independent)
    show_choice_only = st.checkbox("Show only Choice Pantries")
    if show_choice_only:
        agencies_nearby = agencies_nearby[agencies_nearby["choice"] == 1]

    if not agencies_nearby.empty:
        agencies_nearby = agencies_nearby.copy()
        agencies_nearby["total_traveltime"] = agencies_nearby["total_traveltime"].round(2)
        agencies_nearby["total_miles"] = agencies_nearby["total_miles"].round(2)

        display_cols = ["agency name", "address","operating hours","contact", "total_traveltime", "total_miles"]
        st.dataframe(agencies_nearby[display_cols].drop_duplicates().sort_values("total_traveltime"))

        # ─── MAP ────────────────────────────────────────────────────────

        user_df = pd.DataFrame({
            "name": ["Your Location"],
            "latitude": [user_lat],
            "longitude": [user_lon],
            "color_r": [0], "color_g": [0], "color_b": [255],
            "tooltip": ["Your Location"]
        })

        agency_map_df = agencies_nearby.copy()
        agency_map_df["color_r"] = 255
        agency_map_df["color_g"] = 0
        agency_map_df["color_b"] = 0
        agency_map_df["tooltip"] = (
            "Agency: " + agency_map_df["agency name"] +
            "<br>Travel Time (min): " + agency_map_df["total_traveltime"].astype(str) +
            "<br>Distance (miles): " + agency_map_df["total_miles"].astype(str)
        )
        #agency_map_df = agency_map_df.rename(columns={"latitude": "latitude", "longitude": "longitude"})

        combined_df = pd.concat([user_df, agency_map_df], ignore_index=True)

        layer = pdk.Layer(
            "ScatterplotLayer",
            combined_df,
            get_position='[longitude, latitude]',
            get_color='[color_r, color_g, color_b]',
            get_radius=250,
            pickable=True,
        )

        tooltip = {"html": "{tooltip}", "style": {"color": "white"}}

        view_state = pdk.ViewState(
            longitude=user_lon, latitude=user_lat, zoom=10, pitch=0
        )

        deck = pdk.Deck(
            map_style='mapbox://styles/mapbox/light-v9',
            initial_view_state=view_state,
            layers=[layer],
            tooltip=tooltip
        )

        st.pydeck_chart(deck)
    else:
        st.warning("No agencies found within your search radius.")
