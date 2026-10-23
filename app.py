
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
CSV_FILE = ROOT / "DAILY_NATIONAL_RATINGS.csv"

METRICS = [
    "Best Last 45 Days", "Best Last 90 Days", "Best Last 180 Days",
    "Best Same Course", "Best Same Course & Distance", "Best Same Bends",
]

st.set_page_config(
    page_title="Greyhound NATIONAL Ratings",
    page_icon="🐕",
    layout="wide",
)

st.title("Greyhound NATIONAL Ratings")
st.caption("Daily racecards | NATIONAL ratings | Best Last 90 Days selections")

if not CSV_FILE.exists():
    st.error(
        "DAILY_NATIONAL_RATINGS.csv was not found. "
        "Place it in the same folder as this dashboard."
    )
    st.stop()


@st.cache_data
def load_data(path, modified):
    df = pd.read_csv(path, encoding="utf-8-sig")

    df["Date"] = pd.to_datetime(
        df["Date"], format="mixed", dayfirst=True, errors="coerce"
    )

    missing = [col for metric in METRICS for col in (metric, metric + " Runs") if col not in df.columns]
    if missing:
        st.error("The daily CSV is still in the older five-indicator format. Please generate the six-indicator DAILY_NATIONAL_RATINGS.csv using your updated private ratings builder before publishing V2.")
        st.code("Missing columns: " + ", ".join(missing))
        st.stop()

    for metric in METRICS:
        df[metric] = pd.to_numeric(
            df[metric], errors="coerce"
        )
        df[metric + " Runs"] = pd.to_numeric(
            df[metric + " Runs"], errors="coerce"
        ).fillna(0).astype(int)

    df["Trap"] = pd.to_numeric(
        df["Trap"], errors="coerce"
    )
    df["Top 3 Pick"] = pd.to_numeric(
        df["Top 3 Pick"], errors="coerce"
    )

    return df


df = load_data(CSV_FILE, CSV_FILE.stat().st_mtime_ns)

# Sidebar filters
st.sidebar.header("Race Selection")

dates = sorted(df["Date"].dropna().unique(), reverse=True)

if not dates:
    st.error("No valid racecard dates were found.")
    st.stop()

selected_date = st.sidebar.selectbox(
    "Date",
    dates,
    format_func=lambda d: pd.Timestamp(d).strftime("%d/%m/%Y"),
)

day = df[df["Date"] == selected_date].copy()

tracks = sorted(day["Track"].dropna().unique())

selected_track = st.sidebar.selectbox("Track", tracks)

track_df = day[day["Track"] == selected_track].copy()

races = (
    track_df[
        ["Race Number", "Race Time", "Grade", "Distance"]
    ]
    .drop_duplicates()
    .sort_values("Race Time")
)

race_options = []

for _, r in races.iterrows():
    race_options.append(
        (
            r["Race Number"],
            r["Race Time"],
            f'{r["Race Time"]} | Race {r["Race Number"]} '
            f'| {r["Grade"]} | {r["Distance"]}',
        )
    )

selected_race = st.sidebar.selectbox(
    "Race",
    race_options,
    format_func=lambda x: x[2],
)

race = track_df[
    (track_df["Race Number"] == selected_race[0])
    & (track_df["Race Time"] == selected_race[1])
].copy()

race = race.sort_values("Trap")

st.subheader(
    f"{selected_track} — {selected_race[1]}"
)

st.caption(
    f'Race {selected_race[0]} | '
    f'{race.iloc[0]["Grade"]} | '
    f'{race.iloc[0]["Distance"]} | '
    f'{race.iloc[0]["Racing"]}'
)

# Handicap comparison is calculated in memory only.
# The underlying NATIONAL ratings and CSV remain unchanged.
import re


def handicap_metres(value):
    if pd.isna(value) or str(value).strip() == "":
        return 0
    match = re.fullmatch(r"R(\d+)", str(value).strip().upper())
    if not match:
        return None  # Do not silently interpret unexpected handicap codes.
    return int(match.group(1))


def handicap_adjusted(national, distance, allowance):
    if pd.isna(national) or allowance is None:
        return float("nan")
    if distance <= 0 or not (0 <= allowance < distance):
        return float("nan")
    return 1000 * (
        (0.9 + national / 1000) * distance / (distance - allowance) - 0.9
    )


is_handicap = str(race.iloc[0]["Grade"]).strip().upper() == "HP"

if is_handicap:
    # The display switch is available only for HP races.
    view = st.radio(
        "NATIONAL rating view",
        ["Today's adjusted", "Original NATIONAL"],
        horizontal=True,
        key="handicap_view",
    )
    show_adjusted = view == "Today's adjusted"
    st.caption(
        "Today's adjusted ratings are provisional estimates based on each "
        "dog's head start. Original NATIONAL performances are never changed."
    )
else:
    show_adjusted = False

race["Handicap Metres"] = race["Handicap"].apply(handicap_metres)
if is_handicap and race["Handicap Metres"].isna().any():
    st.warning("Unrecognised handicap code: affected adjusted ratings are blank.")

for metric in METRICS:
    adjusted_col = metric + " Adjusted"
    if is_handicap:
        race[adjusted_col] = race.apply(
            lambda dog: handicap_adjusted(
                dog[metric],
                float(re.search(r"\d+(?:\.\d+)?", str(dog["Distance"])).group())
                if re.search(r"\d+(?:\.\d+)?", str(dog["Distance"]))
                else 0,
                dog["Handicap Metres"],
            ),
            axis=1,
        )
    else:
        race[adjusted_col] = race[metric]

# Show all six metrics consistently in the selected view.
active_columns = {
    metric: metric + " Adjusted" if show_adjusted else metric
    for metric in METRICS
}
ranking_metric = active_columns["Best Last 90 Days"]

st.markdown("### Race at a Glance")
ranked = (
    race.dropna(subset=[ranking_metric])
    .sort_values(ranking_metric, ascending=False)
    .head(3)
)

columns = st.columns(3)
for index, column in enumerate(columns):
    with column:
        if index < len(ranked):
            dog = ranked.iloc[index]
            with st.container(border=True):
                st.caption(["1st Rated", "2nd Rated", "3rd Rated"][index])
                st.markdown(f'**T{int(dog["Trap"])} — {dog["Greyhound"]}**')
                st.metric(
                    "Adjusted Best Last 90 Days" if show_adjusted else "Best Last 90 Days",
                    f'{dog[ranking_metric]:.2f}',
                )
        else:
            st.caption("No rated selection")

st.markdown("### Full Racecard")

# Show the selected rating values under familiar column names.
display = race.copy()
for metric in METRICS:
    display[metric] = race[active_columns[metric]]

columns_to_show = [
    "Trap", "Greyhound", "Form", "Trainer", "Handicap",
    *METRICS,
]


def highlight_ratings(column):
    valid = column.dropna().sort_values(ascending=False)
    top_indices = valid.head(2).index.tolist()
    return [
        (
            "background-color: #225b46; color: white;"
            if idx == top_indices[0]
            else "background-color: #695322; color: white;"
            if len(top_indices) > 1 and idx == top_indices[1]
            else ""
        ) if top_indices else ""
        for idx in column.index
    ]


styled = display[columns_to_show].style.format(
    {metric: "{:.2f}" for metric in METRICS},
    na_rep="—",
)
for metric in METRICS:
    styled = styled.apply(highlight_ratings, subset=[metric])

# Short visual headings; underlying metric names and calculations stay unchanged.
short_labels = {
    "Best Last 45 Days": "Last 45 Days",
    "Best Last 90 Days": "Last 90 Days",
    "Best Last 180 Days": "Last 180 Days",
    "Best Same Course": "Course 180",
    "Best Same Course & Distance": "C&D 180",
    "Best Same Bends": "Bends 180",
}
st.dataframe(
    styled, width="stretch", hide_index=True, height=320,
    column_config={
        **{name: st.column_config.NumberColumn(label, width=100, format="%.2f")
           for name, label in short_labels.items()},
        "Trap": st.column_config.NumberColumn("Trap", width=55),
        "Form": st.column_config.TextColumn("Form", width=70),
        "Handicap": st.column_config.TextColumn("Hcap", width=65),
        "Greyhound": st.column_config.TextColumn("Greyhound", width=145),
        "Trainer": st.column_config.TextColumn("Trainer", width=95),
    },
)
if show_adjusted:
    st.caption("All six NATIONAL indicators are adjusted for today's handicap allowances.")

st.markdown("### Greyhound Details")
selected_dog = st.selectbox("Select greyhound", race["Greyhound"].tolist())
dog = race[race["Greyhound"] == selected_dog].iloc[0]

if dog["Match Status"] == "NO GBGB HISTORY FOUND":
    st.info("NEWCOMER — NO RATED RUNS")
elif str(dog["Match Status"]).startswith("CHECK:"):
    st.warning("Historical identity requires verification.")

if is_handicap:
    allowance = dog["Handicap Metres"]
    st.caption(
        f"Today's allowance: {int(allowance)} metres"
        if pd.notna(allowance) else "Today's allowance: unrecognised code"
    )

detail_cols = st.columns(6)
for col, metric in zip(detail_cols, METRICS):
    with col:
        value = dog[active_columns[metric]]
        count = int(dog[metric + " Runs"])
        st.metric(metric, f"{value:.2f}" if pd.notna(value) else "—")
        st.caption(f"{count} qualifying rated runs")

st.caption(
    "All indicators use the maximum qualifying NATIONAL rating strictly before the "
    "racecard date. The 45-, 90- and 180-day indicators use their respective "
    "lookback windows; course, exact course/distance and bends use 180 days. "
    "Best Last 90 Days is the flagship selection rating."
)

st.divider()
st.caption(
    "Source: DAILY_NATIONAL_RATINGS.csv | "
    "All handicap adjustments are display-only; historical GBGB data is unchanged."
)

# ---------- Historical NATIONAL performance (read-only) ----------
# This section never updates the GBGB database or original rating records.
st.divider()
st.header("Historical NATIONAL performance")

try:
    import plotly.graph_objects as go
except ImportError:
    st.warning("Install plotly to view historical charts.")
    st.stop()

HISTORY_CSV = ROOT / "PUBLIC_HISTORY.csv.gz"
if not HISTORY_CSV.exists():
    st.warning("PUBLIC_HISTORY.csv.gz is missing. Run BUILD_PUBLIC_SNAPSHOT.py locally, then upload its output.")
    st.stop()

@st.cache_data(show_spinner="Loading published historical NATIONAL ratings…")
def load_public_history(path, modified):
    rows = pd.read_csv(path, compression="gzip", low_memory=False)
    rows['race_date'] = pd.to_datetime(rows['race_date'], format='mixed', dayfirst=True, errors='coerce')
    rows['national'] = pd.to_numeric(rows['national'], errors='coerce')
    rows['selected_name'] = rows['selected_name'].astype(str).str.upper().str.replace(r'[^A-Z0-9]', '', regex=True)
    return rows.dropna(subset=['race_date'])

all_names = tuple(race['Greyhound'].astype(str).tolist())
public_history = load_public_history(HISTORY_CSV, HISTORY_CSV.stat().st_mtime_ns)
normalized_names = [re.sub(r'[^A-Z0-9]', '', n.upper()) for n in all_names]
selected_race_date = pd.to_datetime(race['Date'].iloc[0])
history = public_history[
    public_history['selected_name'].astype(str).str.upper().str.replace(r'[^A-Z0-9]', '', regex=True).isin(normalized_names)
    & (public_history['race_date'] < selected_race_date)
].copy()
if history.empty:
    st.info('No historical records in the published snapshot for this race.')
    st.stop()

# Identify the dog clicked in the main racecard; the existing dropdown remains a fallback.
# Streamlit supports row selection via dataframe on_select on current versions.
st.caption("Click a greyhound below to open its career history. You can also use the selector.")
click_frame = race[['Trap', 'Greyhound']].reset_index(drop=True)
try:
    chosen = st.dataframe(
        click_frame, hide_index=True, use_container_width=True,
        on_select='rerun', selection_mode='single-row', key='career_click',
    )
    selected_rows = chosen.selection.rows
except (TypeError, AttributeError):
    selected_rows = []
if selected_rows:
    st.session_state['career_selected_name'] = click_frame.iloc[selected_rows[0]]['Greyhound']

names = race['Greyhound'].astype(str).tolist()
current_name = st.session_state.get('career_selected_name', names[0])
if current_name not in names:
    current_name = names[0]
career_name = st.selectbox('Career history for', names, index=names.index(current_name))
st.session_state['career_selected_name'] = career_name

# Adjust using TODAY'S distance and allowance, not the historical allowance.
todays_distance_match = re.search(r'\d+(?:\.\d+)?', str(race.iloc[0]['Distance']))
todays_distance = float(todays_distance_match.group()) if todays_distance_match else 0.0
allowances = {
    re.sub(r'[^A-Z0-9]', '', str(row['Greyhound']).upper()): row['Handicap Metres']
    for _, row in race.iterrows()
}
history['todays_allowance'] = history['selected_name'].map(allowances)
if is_handicap:
    history['adjusted_national'] = history.apply(
        lambda r: handicap_adjusted(r['national'], todays_distance, r['todays_allowance']), axis=1
    )
else:
    history['adjusted_national'] = history['national']

limit_choice = st.radio('Historical runs per greyhound', ['5', '10', '20', 'All'],
                        index=1, horizontal=True, key='history_run_limit')
limit = None if limit_choice == 'All' else int(limit_choice)
chart_metric = 'adjusted_national' if show_adjusted else 'national'
st.caption('Timeline uses actual race dates. Each greyhound has its own most recent run limit.')

plot = go.Figure()
for name in names:
    dog_history = history[history['selected_name'] == re.sub(r'[^A-Z0-9]', '', name.upper())].sort_values('race_date')
    if limit is not None:
        dog_history = dog_history.tail(limit)
    dog_history = dog_history.dropna(subset=[chart_metric])
    if dog_history.empty:
        continue
    def format_text(r):
        def v(x):
            return '—' if pd.isna(x) or str(x).strip() == '' else str(x)
        return (
            f"<b>{name}</b><br>Race: {r['race_date']:%d/%m/%Y}<br>"
            f"Track: {v(r['track'])}<br>Distance: {v(r['distance'])}m<br>"
            f"Grade: {v(r['grade'])}<br>Position: {v(r['position'])}<br>"
            f"Beaten distance: {v(r['beaten_distance'])}<br>"
            f"Running time: {v(r['run_time'])}s<br>"
            f"Historical handicap: {v(r['historical_handicap'])}<br>"
            f"Today's allowance: {v(r['todays_allowance'])}m<br>"
            f"Trap: {v(r['trap'])}<br>Going: {v(r['going'])}<br>"
            f"Sectional: {v(r['sectional'])}<br>"
            f"Original NATIONAL: {r['national']:.2f}<br>"
            f"Today's adjusted NATIONAL: {r['adjusted_national']:.2f}"
            if pd.notna(r['adjusted_national']) else
            f"<b>{name}</b><br>{r['race_date']:%d/%m/%Y}<br>Original NATIONAL: {r['national']:.2f}<br>Adjusted: unavailable"
        )
    plot.add_trace(go.Scatter(
        x=dog_history['race_date'], y=dog_history[chart_metric],
        mode='lines+markers', name=name,
        text=[format_text(r) for _, r in dog_history.iterrows()],
        hovertemplate='%{text}<extra></extra>', connectgaps=False,
    ))
plot.update_layout(
    xaxis_title='Race date',
    yaxis_title='Adjusted NATIONAL' if show_adjusted else 'Original NATIONAL',
    hovermode='closest', legend_title='Greyhound', height=510,
    margin=dict(l=20,r=20,t=20,b=20),
)
st.plotly_chart(plot, use_container_width=True)
st.caption('Click a greyhound in the chart legend to hide/show its line. '
           'Adjusted NATIONAL is a provisional comparison model, not an original recorded rating.')

st.subheader(f'{career_name} — career history')
career = history[history['selected_name'] == re.sub(r'[^A-Z0-9]', '', career_name.upper())].sort_values('race_date', ascending=False)
if career.empty:
    st.info('No NATIONAL-rated historical races found for this greyhound.')
else:
    career = career.rename(columns={
        'race_date':'Date', 'track':'Track', 'distance':'Distance', 'grade':'Grade',
        'position':'Position', 'beaten_distance':'Beaten distance',
        'run_time':'Running time', 'historical_handicap':'Handicap',
        'trap':'Trap', 'going':'Going', 'sectional':'Sectional',
        'national':'NATIONAL', 'adjusted_national':'Adj NATIONAL'
    })
    st.dataframe(career[[
        'Date','Track','Distance','Grade','Position','Beaten distance',
        'Running time','Handicap','Trap','Going','Sectional',
        'NATIONAL','Adj NATIONAL'
    ]], hide_index=True, use_container_width=True,
        column_config={
            'Date': st.column_config.DateColumn(format='DD/MM/YYYY'),
            'Handicap': st.column_config.TextColumn('Handicap', width='small'),
            'NATIONAL':st.column_config.NumberColumn(format='%.2f'),
            'Adj NATIONAL':st.column_config.NumberColumn(format='%.2f'),
        })
    st.download_button('Download career history CSV',
        data=career.to_csv(index=False).encode('utf-8-sig'),
        file_name='career_' + re.sub(r'[^A-Za-z0-9_-]+','_',career_name) + '.csv',
        mime='text/csv')
