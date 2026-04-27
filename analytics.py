import pandas as pd
import glob
import os
import plotly.express as px
import numpy as np

# Copy existing logic to get data
path = 'data'
all_files = glob.glob(os.path.join(path, "*.csv"))

if not all_files:
    print("No files found. Please run the scraper to continue!")
    exit()

# Combining the data
df_list = []
for file in all_files:
    temp_df = pd.read_csv(file) # type: ignore
    df_list.append(temp_df)

# Type checker
df = pd.concat(df_list, ignore_index=True)
df = df.drop_duplicates()

# Get columns
df.columns = [str(col).upper().strip() for col in df.columns]

if 'STARTERS' in df.columns:
    df.rename(columns={'STARTERS': 'PLAYER'}, inplace=True)
elif 'NAME' in df.columns:
    df.rename(columns={'NAME': 'PLAYER'}, inplace=True)

if 'NO.' in df.columns and 'PLAYER' in df.columns:
    df['PLAYER'] = df['NO.'].astype(str).str.replace('.0', '', regex=False) + " - " + df['PLAYER'].astype(str)
elif 'NO' in df.columns and 'PLAYER' in df.columns:
    df['PLAYER'] = df['NO'].astype(str).str.replace('.0', '', regex=False) + " - " + df['PLAYER'].astype(str)

df = df.loc[:, ~df.columns.duplicated()].copy()

col_mapping = {'MP': 'MIN', 'REB': 'TRB', 'TREB': 'TRB', 'TO': 'TOV', 'A': 'AST', 'OREB': 'ORB', 'O-REB': 'ORB'}
df.rename(columns=col_mapping, inplace=True)

if 'FGA' not in df.columns and 'FG' in df.columns:
    df['FGA'] = df['FG'].apply(lambda x: str(x).split('-')[1] if '-' in str(x) else 0)
if 'FTA' not in df.columns and 'FT' in df.columns:
    df['FTA'] = df['FT'].apply(lambda x: str(x).split('-')[1] if '-' in str(x) else 0)

def clean_minutes(min_val):
    if pd.isna(min_val): return 0
    min_str = str(min_val)
    if ':' in min_str:
        try:
            parts = min_str.split(':')
            return int(parts[0]) + int(parts[1]) / 60.0
        except ValueError:
            return 0
    try:
        return float(min_str)
    except ValueError:
        return 0

df['MIN'] = df['MIN'].apply(clean_minutes)

stat_cols = ['FGA', 'FTA', 'ORB', 'TOV', 'PTS', 'TRB', 'AST', 'STL', 'BLK']
for col in stat_cols:
    if col not in df.columns:
        df[col] = 0
    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

# Separate totals
# Filter for A&M
is_true_aggies = df['TEAM'].str.contains("Texas A&M", case=False, na=False) & ~df['TEAM'].str.contains("East|Commerce|Corpus|Kingsville|International", case=False, na=False)

# Totals for A&M players
df_totals = df[df['PLAYER'].str.contains('Totals', case=False, na=False) & is_true_aggies].copy()
df_totals = df_totals[['GAME_ID', 'MIN', 'FGA', 'FTA', 'TOV']].rename(
    columns={'MIN': 'Team_MIN', 'FGA': 'Team_FGA', 'FTA': 'Team_FTA', 'TOV': 'Team_TOV'}
)

# Gets A&M players
df_players = df[(~df['PLAYER'].str.contains('Totals', case=False, na=False)) & is_true_aggies].copy()
df_players = df_players[df_players['MIN'] > 0] # Drop players who didn't play

# Combines players and totals
df_players = pd.merge(df_players, df_totals, on='GAME_ID', how='left')

# Calculations

# True Shooting Percentage (TS%)
ts_denominator = 2 * (df_players['FGA'] + 0.44 * df_players['FTA'])
df_players['TS_PCT'] = np.where(ts_denominator > 0, df_players['PTS'] / ts_denominator, 0)

# Usage Percentage (USG%)
usg_numerator = (df_players['FGA'] + 0.44 * df_players['FTA'] + df_players['TOV']) * (df_players['Team_MIN'] / 5)
usg_denominator = df_players['MIN'] * (df_players['Team_FGA'] + 0.44 * df_players['Team_FTA'] + df_players['Team_TOV'])
df_players['USG_PCT'] = np.where(usg_denominator > 0, 100 * (usg_numerator / usg_denominator), 0)

# Assist to Turnover Ratio
df_players['AST_TO'] = np.where(df_players['TOV'] > 0, df_players['AST'] / df_players['TOV'], df_players['AST'])

# Season averages
# Group by each player
season_stats = df_players.groupby('PLAYER').agg({
    'MIN': 'sum',
    'PTS': 'sum',
    'AST': 'sum',
    'TOV': 'sum',
    'FGA': 'sum',
    'FTA': 'sum',
    'USG_PCT': 'mean', # Average usage across all games
}).reset_index()

# Filter any players with <30 minutes played
season_stats = season_stats[season_stats['MIN'] >= 30].copy()

# Calculate statistics
season_ts_denom = 2 * (season_stats['FGA'] + 0.44 * season_stats['FTA'])
season_stats['Season_TS_PCT'] = np.where(season_ts_denom > 0, season_stats['PTS'] / season_ts_denom, 0)
season_stats['Season_AST_TO'] = np.where(season_stats['TOV'] > 0, season_stats['AST'] / season_stats['TOV'], season_stats['AST'])


# Create our chart
aggie_colors = ['#500000', '#000000', '#5C5C5C', '#A2A2A6', '#E4E4ED']

fig = px.scatter(
    season_stats,
    x='USG_PCT',
    y='Season_TS_PCT',
    size='MIN',
    color='MIN',
    hover_name='PLAYER',
    hover_data={'USG_PCT': ':.1f', 'Season_TS_PCT': ':.3f', 'Season_AST_TO': ':.2f', 'MIN': True},
    color_continuous_scale=['#A2A2A6', '#500000'],
    size_max=35,
    title="Offensive Role (Usage) vs. Scoring Efficiency (True Shooting %)<br><sup><i>Players with >30 Total Minutes | Larger bubbles = More minutes played</i></sup>",
    labels={'USG_PCT': 'Usage Rate (USG%)', 'Season_TS_PCT': 'True Shooting % (TS%)'}
)

# Create 4 different quadrants
fig.add_hline(y=season_stats['Season_TS_PCT'].mean(), line_dash="dash", line_color="black", annotation_text="Avg Efficiency")
fig.add_vline(x=season_stats['USG_PCT'].mean(), line_dash="dash", line_color="black", annotation_text="Avg Usage")

fig.write_html("advanced_metrics_scatter.html", auto_open=True)
print("Graph created!")

# Graphs vs. Time

# All players with significant minutes played
qualified_players = season_stats['PLAYER'].unique()

# Filter the game-by-game data
df_trends = df_players[df_players['PLAYER'].isin(qualified_players)].copy()

# Create a chronological "Game Number" (1, 2, 3...)
unique_games = sorted(df_trends['GAME_ID'].unique())
game_sequence = {game_id: i + 1 for i, game_id in enumerate(unique_games)}
df_trends['Game_Number'] = df_trends['GAME_ID'].map(game_sequence)
df_trends = df_trends.sort_values(by=['Game_Number'])
df_trends['TS_PCT_DISPLAY'] = df_trends['TS_PCT'] * 100

# Sort players by total minutes
players_by_min = season_stats.sort_values(by='MIN', ascending=False)['PLAYER'].tolist()

# Split into two groups
main_rotation_players = players_by_min[:5]  # Top 5 players
second_unit_players = players_by_min[5:10]  # Next 5

df_main = df_trends[df_trends['PLAYER'].isin(main_rotation_players)].copy()
df_bench = df_trends[df_trends['PLAYER'].isin(second_unit_players)].copy()

# Main Rotation Usage
fig_usg_main = px.line(
    df_main, x='Game_Number', y='USG_PCT', color='PLAYER', markers=True,
    title='Usage Rate (%) - Main Rotation (Top 5 Minutes)',
    labels={'Game_Number': 'Game', 'USG_PCT': 'Usage Rate (%)', 'PLAYER': 'Player'}
)
fig_usg_main.update_xaxes(dtick=1)
fig_usg_main.update_traces(line=dict(width=3), marker=dict(size=8))
fig_usg_main.write_html("usage_main_rotation.html", auto_open=True)

# Second Unit Usage
if not df_bench.empty:
    fig_usg_bench = px.line(
        df_bench, x='Game_Number', y='USG_PCT', color='PLAYER', markers=True,
        title='Usage Rate (%) - Second Unit',
        labels={'Game_Number': 'Game', 'USG_PCT': 'Usage Rate (%)', 'PLAYER': 'Player'}
    )
    fig_usg_bench.update_xaxes(dtick=1)
    fig_usg_bench.update_traces(line=dict(width=2), marker=dict(size=6))
    fig_usg_bench.write_html("usage_second_unit.html", auto_open=True)

# Main Rotation TS%
fig_ts_main = px.line(
    df_main, x='Game_Number', y='TS_PCT_DISPLAY', color='PLAYER', markers=True,
    title='True Shooting (%) - Main Rotation (Top 5 Minutes)',
    labels={'Game_Number': 'Game', 'TS_PCT_DISPLAY': 'True Shooting (%)', 'PLAYER': 'Player'}
)
fig_ts_main.update_xaxes(dtick=1)
fig_ts_main.update_traces(line=dict(width=3), marker=dict(size=8))
fig_ts_main.write_html("ts_main_rotation.html", auto_open=True)

# Second Unit TS%
if not df_bench.empty:
    fig_ts_bench = px.line(
        df_bench, x='Game_Number', y='TS_PCT_DISPLAY', color='PLAYER', markers=True,
        title='True Shooting (%) - Second Unit',
        labels={'Game_Number': 'Game', 'TS_PCT_DISPLAY': 'True Shooting (%)', 'PLAYER': 'Player'}
    )
    fig_ts_bench.update_xaxes(dtick=1)
    fig_ts_bench.update_traces(line=dict(width=2), marker=dict(size=6))
    fig_ts_bench.write_html("ts_second_unit.html", auto_open=True)

print("Split Time Series Trend Graphs Created!")