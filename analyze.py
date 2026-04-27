import pandas as pd
import glob
import os
import plotly.express as px

# Loading the data
path = 'data'
all_files = glob.glob(os.path.join(path, "*.csv"))

if not all_files:
    print("No files found. Please run the scraper to continue!") # If no csv files, prints out error message
    exit()

# Combining the data
df_list = []
for file in all_files:
    temp_df = pd.read_csv(file) # type: ignore
    df_list.append(temp_df)

# Puts in one data frame
df = pd.concat(df_list, ignore_index=True)

# Check for duplicates and handle them
df = df.drop_duplicates()

# Cleaning the data
df.columns = [str(col).upper().strip() for col in df.columns]

if 'STARTERS' in df.columns:
    df.rename(columns={'STARTERS': 'PLAYER'}, inplace=True)
elif 'NAME' in df.columns:
    df.rename(columns={'NAME': 'PLAYER'}, inplace=True)

if 'NO.' in df.columns and 'PLAYER' in df.columns:
    df['PLAYER'] = df['NO.'].astype(str).str.replace('.0', '', regex=False) + " - " + df['PLAYER'].astype(str)
elif 'NO' in df.columns and 'PLAYER' in df.columns:
    df['PLAYER'] = df['NO'].astype(str).str.replace('.0', '', regex=False) + " - " + df['PLAYER'].astype(str)

df = df.loc[:, ~df.columns. duplicated()].copy()

col_mapping = {
    'MP': 'MIN', 'REB': 'TRB', 'TREB': 'TRB',
    'TO': 'TOV', 'A': 'AST', 'OREB': 'ORB', 'O-REB': 'ORB'
}
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

# Isolating totals and calculating number of possessions
df_totals = df[df['PLAYER'].str.contains('Totals', case=False, na=False)].copy()

# Filters for A&M specifically
is_true_aggies = df['TEAM'].str.contains("Texas A&M", case=False, na=False) & ~df['TEAM'].str.contains("East|Commerce|Corpus|Kingsville|International", case=False, na=False)

# Finds the opponent
df_opponents = df[~is_true_aggies].copy()
# Group by the game ID
opponent_mapping = df_opponents.groupby('GAME_ID')['TEAM'].first().reset_index()
opponent_mapping.rename(columns={'TEAM': 'OPPONENT'}, inplace=True)

# Filters the players
# Filters the players (and handles the A&M filter at the exact same time)
df_players = df[(~df['PLAYER'].str.contains('Totals', case=False, na=False)) & is_true_aggies].copy()

# Math to find possessions
df_totals['Poss_Component'] = df_totals['FGA'] + (0.44 * df_totals['FTA']) - df_totals['ORB'] + df_totals['TOV']
game_possessions = df_totals.groupby('GAME_ID')['Poss_Component'].sum() * 0.5
game_possessions = game_possessions.reset_index()
game_possessions.rename(columns={'Poss_Component': 'Game_Possessions'}, inplace=True)

# Combines opponent and team data all together
df_players = pd.merge(df_players, game_possessions, on='GAME_ID', how='left')

# Adds the opponent to the player's data
df_players = pd.merge(df_players, opponent_mapping, on='GAME_ID', how='left')

df_players = df_players[df_players['MIN'] > 0].copy()

df_players['Intensity'] = (df_players['PTS'] + df_players['TRB'] + df_players['AST'] +
                           df_players['STL'] + df_players['BLK'] - df_players['TOV']) / df_players['MIN']

df_players['PAW'] = (df_players['MIN'] / 40) * df_players['Game_Possessions'] * df_players['Intensity']

df_players = df_players.sort_values(by=['PLAYER', 'GAME_ID'])
df_players['Rolling_PAW'] = df_players.groupby('PLAYER')['PAW'].transform(lambda x: x.rolling(window=3, min_periods=1).mean())

# Get game numbers
unique_games = sorted(df_players['GAME_ID'].unique())
game_sequence = {game_id: i + 1 for i, game_id in enumerate(unique_games)}
df_players['Game_Number'] = df_players['GAME_ID'].map(game_sequence)
# Sort correctly
df_players = df_players.sort_values(by=['PLAYER', 'Game_Number'])
# ------------------------------------------------------------------

# Graph 1: PAW vs. Time
top_players = df_players.groupby('PLAYER')['MIN'].sum().nlargest(5).index
df_top = df_players[df_players['PLAYER'].isin(top_players)]

# Saves hex values of A&M themed colors
aggie_colors = ['#500000', '#000000', '#5C5C5C', '#A2A2A6', '#E4E4ED']

fig_line = px.line(
    df_top,
    x='Game_Number',
    y='Rolling_PAW',
    color='PLAYER',
    markers=True,
    color_discrete_sequence=aggie_colors,
    title='Player Workload (3-Game Rolling PAW) - Top 5 Players by Minutes<br><sup><i>PAW = (MIN / 40) × Game_Possessions × Intensity  |  Intensity = (PTS + TRB + AST + STL + BLK - TOV) / MIN</i></sup>',
    labels={'Game_Number': 'Game of the Season', 'Rolling_PAW': 'Rolling PAW', 'PLAYER': 'Player'}
)
fig_line.update_xaxes(dtick=1)
fig_line.update_traces(line=dict(width=3), marker=dict(size=8))
fig_line.write_html("paw_line_chart.html", auto_open=True)


# Graph 2: Efficiency Scatterplot
fig_scatter = px.scatter(
    df_players,
    x='PAW',
    y='Intensity',
    color='MIN',
    size='MIN',
    hover_name='PLAYER',
    hover_data={'OPPONENT': True, 'GAME_ID': False, 'PAW': ':.2f', 'Intensity': ':.2f', 'PTS': True, 'TRB': True, 'MIN': True},
    color_continuous_scale=['#A2A2A6', '#500000'],
    size_max=25,
    opacity=0.8,
    title='Workload (PAW) vs. Efficiency (Intensity)<br><sup><i>PAW = (MIN / 40) × Game_Possessions × Intensity  |  Intensity = (PTS + TRB + AST + STL + BLK - TOV) / MIN</i></sup>',
    labels={'PAW': 'Player Action Workload (PAW)', 'Intensity': 'Intensity (Stats per Minute)'}
)

avg_intensity = df_players['Intensity'].mean()
avg_paw = df_players['PAW'].mean()

fig_scatter.add_hline(y=avg_intensity, line_dash="dash", line_color="black", annotation_text="Avg Intensity")
fig_scatter.add_vline(x=avg_paw, line_dash="dash", line_color="black", annotation_text="Avg Workload")
fig_scatter.write_html("paw_scatter_chart.html", auto_open=True)

print("Graphs Created!")