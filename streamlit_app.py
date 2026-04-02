import json
import os
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st


def load_geojson(file_path):
    if not os.path.isfile(file_path):
        return None
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_polygons(geometry):
    geom_type = geometry.get("type")
    if geom_type == "Polygon":
        return [geometry.get("coordinates", [])]
    if geom_type == "MultiPolygon":
        return geometry.get("coordinates", [])
    return []


def build_map(states_geo, energy_geo, police_geo, show_states, show_energy, show_police):
    fig = go.Figure()

    if show_states and states_geo:
        boundary_drawn = False
        for feature in states_geo.get("features", []):
            props = feature.get("properties", {})
            name = props.get("NAME_1") or props.get("NAME") or props.get("state") or "State"
            for polygon in extract_polygons(feature.get("geometry", {})):
                for ring in polygon:
                    lon = [point[0] for point in ring]
                    lat = [point[1] for point in ring]
                    fig.add_trace(
                        go.Scattermapbox(
                            lon=lon,
                            lat=lat,
                            mode="lines",
                            fill="toself",
                            fillcolor="rgba(72, 61, 139, 0.08)",
                            line=dict(color="rgba(72, 61, 139, 0.75)", width=1.5),
                            name="State boundaries" if not boundary_drawn else "",
                            legendgroup="State boundaries",
                            showlegend=not boundary_drawn,
                            hoverinfo="text",
                            text=name,
                        )
                    )
                    boundary_drawn = True

    energy_lons = []
    energy_lats = []
    energy_text = []
    if show_energy and energy_geo:
        for feature in energy_geo.get("features", []):
            geometry = feature.get("geometry", {})
            props = feature.get("properties", {})
            if geometry.get("type") == "Point":
                lon, lat = geometry.get("coordinates", [None, None])
                if lon is not None and lat is not None:
                    energy_lons.append(lon)
                    energy_lats.append(lat)
                    energy_text.append(props.get("name", "Energy plant"))

    if energy_lons:
        fig.add_trace(
            go.Scattermapbox(
                lon=energy_lons,
                lat=energy_lats,
                mode="markers",
                marker=dict(size=10, color="#ffba00", symbol="star"),
                name="Energy plants",
                legendgroup="Energy plants",
                text=energy_text,
                hoverinfo="text",
            )
        )

    police_lons = []
    police_lats = []
    police_text = []
    if show_police and police_geo:
        for feature in police_geo.get("features", []):
            geometry = feature.get("geometry", {})
            props = feature.get("properties", {})
            if geometry.get("type") == "Point":
                lon, lat = geometry.get("coordinates", [None, None])
                if lon is not None and lat is not None:
                    police_lons.append(lon)
                    police_lats.append(lat)
                    police_text.append(props.get("name", "Police station"))

    if police_lons:
        fig.add_trace(
            go.Scattermapbox(
                lon=police_lons,
                lat=police_lats,
                mode="markers",
                marker=dict(size=8, color="#1f77b4", symbol="circle"),
                name="Police stations",
                legendgroup="Police stations",
                text=police_text,
                hoverinfo="text",
            )
        )

    if not fig.data:
        fig.add_annotation(
            text="No geojson layers could be loaded. Check that the files exist in the repository.",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font=dict(size=16, color="#444"),
        )

    fig.update_layout(
        mapbox_style="open-street-map",
        mapbox_center={"lat": 22.0, "lon": 80.0},
        mapbox_zoom=4,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        legend=dict(title="India GeoJSON layers", orientation="h", y=1.03, x=0),
    )

    return fig


def summarize_geojson(geojson, label):
    if not geojson:
        return f"{label}: file not loaded."
    count = len(geojson.get("features", []))
    return f"{label}: {count} features"


def main():
    st.set_page_config(page_title="India GeoJSON Viewer", layout="wide")
    st.title("India Combined GeoJSON Map")
    st.write(
        "This Streamlit app hosts a combined map of `INDIA_STATES.geojson`, `INDIA_ENERGY_PLANTS.geojson`, and `INDIA_POLICE_STATIONS.geojson`."
    )

    base_path = Path(__file__).resolve().parent
    states_geo = load_geojson(base_path / "INDIA_STATES.geojson")
    energy_geo = load_geojson(base_path / "INDIA_ENERGY_PLANTS.geojson")
    police_geo = load_geojson(base_path / "INDIA_POLICE_STATIONS.geojson")

    st.sidebar.header("Display options")
    show_states = st.sidebar.checkbox("Show state boundaries", True)
    show_energy = st.sidebar.checkbox("Show energy plants", True)
    show_police = st.sidebar.checkbox("Show police stations", True)

    fig = build_map(states_geo, energy_geo, police_geo, show_states, show_energy, show_police)
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("GeoJSON summary", expanded=True):
        st.write(summarize_geojson(states_geo, "States"))
        st.write(summarize_geojson(energy_geo, "Energy plants"))
        st.write(summarize_geojson(police_geo, "Police stations"))

    st.markdown(
        "---\n"
        "**How to run:** `streamlit run streamlit_app.py`"
    )


if __name__ == "__main__":
    main()
