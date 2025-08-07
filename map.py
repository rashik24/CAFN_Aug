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

HOURS_CSV = "fbcenc_hourly.csv"
ODM_CSV = "ODM_CAFN.csv"
TRACTS_SHP = "cb_2023_37_tract_500k.shp"
OPENCAGE_API_KEY = "f53bdda785074d5499b7a4d29d5acd1f"
geocoder = OpenCageGeocode(OPENCAGE_API_KEY)

# ─── STREAMLIT APP ───────────────────────────────────────────────────────

st.set_page_config(page_title="Open Food Pantries", layout="wide")
st.title("Open Food Pantries Finder")

mode = st.radio("Choose input mode:", ["Address", "ZIP Code"])

user_lat, user_lon, user_geoid = None, None, None

if mode == "Address":
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

elif mode == "ZIP Code":
    zip_code = st.text_input("Enter your ZIP code:")

hourly_df = pd.read_csv(HOURS_CSV)
hourly_df.columns = hourly_df.columns.str.strip().str.lower()
hourly_df["day"] = hourly_df["day"].str.strip().str.title()

odm_df = pd.read_csv(ODM_CSV)
odm_df.columns = odm_df.columns.str.strip().str.lower()
odm_df["geoid"] = odm_df["geoid"].astype(int)

tracts_gdf = gpd.read_file(TRACTS_SHP).to_crs(epsg=4326)
if tracts_gdf["GEOID"].dtype == object:
    tracts_gdf["GEOID"] = tracts_gdf["GEOID"].astype(int)

if mode == "Address" and user_lat is not None and user_lon is not None:
    user_point = Point(user_lon, user_lat)
    matched_tract = tracts_gdf[tracts_gdf.contains(user_point)]
    if not matched_tract.empty:
        user_geoid = matched_tract.iloc[0]["GEOID"]
        st.success(f"Matched your location to GEOID {user_geoid}")
    else:
        st.error("Could not match your location to a census tract.")
        st.stop()
elif mode == "ZIP Code" and zip_code:
    odm_df = odm_df[odm_df["zip"].astype(str) == zip_code]
    if odm_df.empty:
        st.warning("No agencies found in that ZIP code.")
        st.stop()
    user_geoid = None

if user_geoid is not None:
    agencies_from_user_geoid = odm_df[
        (odm_df["geoid"] == user_geoid) &
        (odm_df["total_traveltime"] <= 20)
    ]
    if agencies_from_user_geoid.empty:
        st.warning("No agencies linked to your tract. Searching all nearby agencies instead.")
        agencies_from_user_geoid = odm_df[odm_df["total_traveltime"] <= 60]
else:
    agencies_from_user_geoid = odm_df

# Remaining logic remains unchanged (date/time selection, filters, results, map)
# You can continue the rest of the logic as is, using agencies_from_user_geoid as the base DataFrame
