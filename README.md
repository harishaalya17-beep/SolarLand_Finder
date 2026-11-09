# SolarLand Finder

**Land Evaluation and Monitoring System**

## Project Overview
SolarLand Finder is a prototype application designed to evaluate potential land parcels around a selected PMU (Main Intake Substation) or target location.

## Main Features
- Search for an existing PMU or custom target location.
- Display the target location on an interactive map.
- Show 5 km and 8 km reference zones.
- Display land parcel information and estimated land sizes.
- Calculate reference distances and road distances.
- Classify land parcels into Good Fit, Worth a Look, and No Good.
- Display a land evaluation dashboard.
- Export evaluation results to CSV and Excel.

## Technologies Used
- Python
- Streamlit
- Pandas
- Folium
- Geopy
- OpenStreetMap

## How to Run

Install the required libraries:

```bash
pip install -r requirements.txt
```

Run the application:

```bash
streamlit run app.py
```

## Data Disclaimer
This is a demonstration prototype. The current parcel records and locations use simulated data and do not represent verified vacant land. Distance and evaluation results should be validated using actual land and road-network data before practical use.
