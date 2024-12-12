# Import python packages
import streamlit as st
import shap
from snowflake.ml.registry import Registry
from datetime import datetime
from snowflake.snowpark.context import get_active_session
import plotly.express as px
import pandas as pd
import matplotlib.pyplot as plt
import plotly.graph_objects as go
import streamlit.components.v1 as components
from streamlit_extras.stylable_container import stylable_container
import io

# Write directly to the app
st.set_page_config(layout='wide')
st.title("Player360")

# Get the current credentials
session = get_active_session()

@st.cache_data(show_spinner=False)
def load_query(query):
    query = session.sql(query).to_pandas()
    return query
    
@st.cache_data(show_spinner=False)
def load_table(table_name):
    table = session.table(table_name).to_pandas()
    return table

@st.cache_data(show_spinner=False)
def split_frame(input_df, rows):
    df = [input_df.loc[i : i + rows - 1, :] for i in range(0, len(input_df), rows)]
    return df

def cache_model(model_name,version,load=False):
    mv = reg.get_model(model_name).version(version)
    if load:
        mv = mv.load()
    return mv

@st.cache_data(show_spinner=False)
def save_filter(input_df, param, start_date, end_date = None):
    if end_date:
        df = input_df[
            (input_df[param] >= start_date) &
            (input_df[param] <= end_date)]
    else:
        df = input_df[input_df[param] >= start_date]
    return df

def create_pagination(dataset :pd.DataFrame, key :str):
    top_menu = st.columns(3)
    with top_menu[0]:
        sort = st.radio("Sort Data", options=["Yes", "No"], horizontal=1, index=1, key=f"{key}_sort")
    if sort == "Yes":
        with top_menu[1]:
            sort_field = st.selectbox("Sort By", options=dataset.columns, key=f"{key}_sort_by")
        with top_menu[2]:
            sort_direction = st.radio(
                "Direction", options=["⬆️", "⬇️"], horizontal=True,  key=f"{key}_sort_values"
            )
        dataset = dataset.sort_values(
            by=sort_field, ascending=sort_direction == "⬆️", ignore_index=True
        )
    pagination = st.container()
    
    bottom_menu = st.columns((4, 1, 1))
    with bottom_menu[2]:
        batch_size = st.selectbox("Page Size", options=[25, 50, 100], key=f"{key}_page_size")
    with bottom_menu[1]:
        total_pages = (
            int(len(dataset) / batch_size) if int(len(dataset) / batch_size) > 0 else 1
        )
        current_page = st.number_input(
            "Page", min_value=1, max_value=total_pages, step=1, key=f"{key}_page_number_input"
        )
    with bottom_menu[0]:
        st.markdown(f"Page **{current_page}** of **{total_pages}** ")
    pages = split_frame(dataset, batch_size)
    pagination.dataframe(data=pages[current_page - 1], use_container_width=True)


users_df = load_table(f"{session.get_current_database()}.RAW.USERS")
retention_df = load_query(f"SELECT * FROM {session.get_current_database()}.ANALYTIC.RETENTION")
ranking_df = load_table(f"{session.get_current_database()}.ANALYTIC.USER_RANKINGS")
demographics_df = load_query(f"SELECT * FROM {session.get_current_database()}.ANALYTIC.DEMOGRAPHICS" )

active_users = retention_df[retention_df['CHURNED'] ==  0]
inactive_users = retention_df[retention_df['CHURNED'] ==  1]

col1,col2,col3 = st.columns(3)


if 'user_id' not in st.session_state:
    st.session_state.user_id = 1001  # Default user_id

components.html("""
  <script>
    window.parent.document.querySelector('[data-testid="stSidebar"]').style.width = "25%";
  </script>
""", height=0)
with st.sidebar:
    user_id = st.number_input(label='PLAYER_ID', min_value=1001, step=1)
    
    # Check if the user_id has changed
    if user_id != st.session_state.user_id:
        st.session_state.user_id = user_id
        st.experimental_rerun()
    if user_id not in users_df['USER_ID'].values:
        st.write("Invalid User ID")

    user_info = users_df[users_df['USER_ID'] == user_id]
    if user_id in list(active_users['USER_ID']):
        st.session_state.active_user = 1
        st.markdown(
            f"""
            <div style="border: 5px solid green; display: inline-block; padding: 10px; text-align: center; width: 100%;">
                <img src="{user_info['PHOTO_URL'].values[0]}" style="display: inline-block; padding: 10px; text-align: center; width: 100%;">
            </div>
            """,
            unsafe_allow_html=True
        )
        status = 'Active'
    else:
        st.session_state.active_user = 0
        st.markdown(
            f"""
            <div style="border: 5px solid red; display: inline-block; padding: 10px; text-align: center; width: 100%;">
                <img src="{user_info['PHOTO_URL'].values[0]}" style="display: inline-block; padding: 10px; text-align: center; width: 100%;">
            </div>
            """,
            unsafe_allow_html=True
        )
        status = 'Inactive'

    st.divider()
    
    # Calculate personal details
    birthdate = user_info['BIRTHDATE'].values[0]
    current_date = datetime.now()
    age = current_date.year - birthdate.year - ((current_date.month, current_date.day) < (birthdate.month, birthdate.day))
    first_login = pd.to_datetime(retention_df.loc[retention_df['USER_ID'] == user_id, 'FIRST_LOGIN_DATE'].values[0])
    last_login = pd.to_datetime(retention_df.loc[retention_df['USER_ID'] == user_id, 'LAST_LOGIN_DATE'].values[0])


    class UserProfileCard:
        def __init__(self, key:str, value:str)->None:
            self.key = key
            self.value = value

        def render_card(self)->None:
            with st.container(border=True, height=35):
                card_columns = st.columns(2)
                with card_columns[0]:
                    st.caption(f"**{self.key}:**")
                with card_columns[1]:
                    st.caption(self.value)

    cards_css = """
    <style>
    div[height="35"]{
        padding-top:3px;
        overflow:hidden;
        border-color:lightgray;
        font-size:8px;
        overflow-wrap: break-word;
        & p {
        color:lightgray;
        }
    }
    </style>
    """
    
    st.markdown(cards_css, unsafe_allow_html=True)

    users_ranking_df = ranking_df[ranking_df['USER_ID'] == user_id]
   
    player_info = {
        "Player Status":status,
        "Name":user_info['FIRST_NAME'].values[0]+' '+user_info['LAST_NAME'].values[0],
        "Gender":user_info['GENDER'].values[0],
        "Email":user_info['EMAIL'].values[0],
        "Age":age,
        "Location":user_info['LOCATION'].values[0],
        "Player Type":demographics_df['PLAYER_TYPE'].values[0],
        "Rank Name": users_ranking_df['RANK_NAME'].values[0],
        "Rank Percentile": users_ranking_df['PERCENTILE'].values[0].round(2),
        "First Login": first_login,
        "Last Login": last_login,
        "Days Inactive":retention_df.loc[retention_df['USER_ID'] == user_id, 'DAYS_SINCE_LAST_LOGIN'].values[0]
    }
    for k,v in player_info.items():
        UserProfileCard(key=k, value=v).render_card()

    
ad_engagement_df = load_query(f"SELECT * FROM {session.get_current_database()}.ANALYTIC.AD_ENGAGEMENT WHERE USER_ID = {user_id}")
# load dataframes here
achievements_df = load_query(f"SELECT * FROM {session.get_current_database()}.RAW.ACHIEVEMENTS WHERE USER_ID = {user_id}")
player_events_points_df = load_query(f'SELECT * FROM {session.get_current_database()}.ANALYTIC.POINTS_PER_EVENT WHERE USER_ID = {user_id} ORDER BY LOG_IN ASC')
support_ticket_df = load_table(f"{session.get_current_database()}.RAW.SUPPORT_TICKETS")
sessions_df = load_query(f"SELECT * FROM {session.get_current_database()}.RAW.SESSIONS WHERE USER_ID = {user_id} ORDER BY LOG_IN ASC")

# all ads
purchases_df = load_query(f"SELECT * FROM {session.get_current_database()}.RAW.PURCHASES WHERE USER_ID = {user_id} ORDER BY TIMESTAMP_OF_PURCHASE ASC")
# all ads that lead to purchases
purchased_df = purchases_df[purchases_df['PURCHASE_TYPE'] != 'none']

st.divider()
date_range = st.radio(label='Active Date Range', options=[30, 60, 90, 365, 'Lifetime'], horizontal=True)

# filter by start date in date range
if date_range != 'Lifetime':
    end_date = last_login
    start_date = end_date - pd.Timedelta(days=date_range)
else:
    end_date = last_login
    start_date=None

def safe_divide(numerator, denominator, default_value=0):
    if denominator == 0:
        return default_value
    else:
        return numerator / denominator

# compute metric deltas
# -----------------------------------------------------------------------------------
if start_date:
    last_seq_total_points = save_filter(player_events_points_df, 'LOG_IN', start_date)['TOTAL_POINTS'].sum()
    prev_seq_start_date = start_date - pd.Timedelta(days=date_range)
    prev_seq_total_points = save_filter(player_events_points_df, 'LOG_IN', prev_seq_start_date, start_date)['TOTAL_POINTS'].sum()
    total_points_delta = last_seq_total_points - prev_seq_total_points
    total_points_delta = total_points_delta.round(2)

    last_seq_total_ads = len(save_filter(purchases_df, 'TIMESTAMP_OF_PURCHASE', start_date))
    prev_seq_total_ads = len(save_filter(purchases_df, 'TIMESTAMP_OF_PURCHASE', prev_seq_start_date, start_date))
    total_ads_delta = last_seq_total_ads - prev_seq_total_ads

    last_seq_total_logins = len(save_filter(player_events_points_df, 'LOG_IN', start_date))
    prev_seq_total_logins = len(save_filter(player_events_points_df, 'LOG_IN', prev_seq_start_date, start_date))
    total_logins_delta = last_seq_total_logins - prev_seq_total_logins

    last_seq_total_purchases = len(save_filter(purchased_df, 'TIMESTAMP_OF_PURCHASE', start_date))
    prev_seq_total_purchases = len(save_filter(purchased_df, 'TIMESTAMP_OF_PURCHASE', prev_seq_start_date, start_date))
    total_purchases_delta = last_seq_total_purchases - prev_seq_total_purchases

    # Calculate proportions and averages with zero check
    last_seq_prop_purchased = safe_divide(last_seq_total_purchases, last_seq_total_ads, default_value=0) * 100
    prev_seq_prop_purchased = safe_divide(prev_seq_total_purchases, prev_seq_total_ads, default_value=0) * 100
    prop_purchased_delta = round(last_seq_prop_purchased - prev_seq_prop_purchased, 2)
    
    # Calculate total purchase amount with zero check
    last_seq_total_purchase_amount = save_filter(purchases_df, 'TIMESTAMP_OF_PURCHASE', start_date)['PURCHASE_AMOUNT'].sum()
    prev_seq_total_purchase_amount = save_filter(purchases_df, 'TIMESTAMP_OF_PURCHASE', prev_seq_start_date, start_date)['PURCHASE_AMOUNT'].sum()
    total_purchase_amount_delta = round(last_seq_total_purchase_amount - prev_seq_total_purchase_amount, 2)
    
    # Calculate average purchase amount with zero check
    last_seq_average_purchase_amount = safe_divide(last_seq_total_purchase_amount, last_seq_total_purchases, default_value=0)
    prev_seq_average_purchase_amount = safe_divide(prev_seq_total_purchase_amount, prev_seq_total_purchases, default_value=0)
    average_purchase_amount_delta = round(last_seq_average_purchase_amount - prev_seq_average_purchase_amount, 2)
    
    # Calculate total ad duration with zero check
    last_seq_total_ad_duration = save_filter(purchases_df, 'TIMESTAMP_OF_PURCHASE', start_date)['AD_ENGAGEMENT_TIME'].sum()
    prev_seq_total_ad_duration = save_filter(purchases_df, 'TIMESTAMP_OF_PURCHASE', prev_seq_start_date, start_date)['AD_ENGAGEMENT_TIME'].sum()
    last_seq_average_ad_duration = safe_divide(last_seq_total_ad_duration, last_seq_total_ads, default_value=0)
    prev_seq_average_ad_duration = safe_divide(prev_seq_total_ad_duration, prev_seq_total_ads, default_value=0)
    average_ad_duration_delta = round(last_seq_average_ad_duration - prev_seq_average_ad_duration, 2)
else:
    last_seq_total_points = users_ranking_df['TOTAL_POINTS'].values[0].round(2)
    total_points_delta = "~"
    
    last_seq_total_ads = ad_engagement_df['TOTAL_ADS'].values[0]
    total_ads_delta = "~"

    last_seq_total_logins = retention_df[retention_df['USER_ID'] == user_id]['TOTAL_LOGINS'].values[0]
    total_logins_delta = "~"

    last_seq_total_purchases = ad_engagement_df['TOTAL_PURCHASES'].values[0]
    total_purchases_delta = "~"

    last_seq_prop_purchased = (ad_engagement_df['PROPORTION_PURCHASED'].values[0] * 100).round(2)
    prop_purchased_delta = "~"

    last_seq_total_purchase_amount = (ad_engagement_df['TOTAL_PURCHASES_AMOUNT'].values[0]).round(2)
    total_purchase_amount_delta = "~"

    last_seq_average_purchase_amount = (ad_engagement_df['AVERAGE_PURCHASE_AMOUNT'].values[0]).round(2)
    average_purchase_amount_delta = "~"

    last_seq_average_ad_duration = (ad_engagement_df['AVERAGE_AD_ENGAGEMENT_TIME'].values[0]).round(2)
    average_ad_duration_delta = "~"
    
# Adds hoverable text explaining the the metric
with stylable_container(
    key="tooltip_container",
    css_styles="""
    {
        position: relative;
        display: inline-block;

        .tooltip-text {
            visibility: hidden;
            width: 250px;
            background-color: black;
            color: #fff;
            text-align: center;
            border-radius: 6px;
            padding: 5px;
            position: absolute;
            z-index: 1;
            bottom: 125%; /* Position the tooltip above the text */
            left: 50%;
            margin-left: -60px;
            opacity: 0;
            transition: opacity 0.3s;
        }

        &:hover .tooltip-text {
            visibility: visible;
            opacity: 1;
        }
    }
    """,
):
    # display metrics
    with st.container(border=True):
        col1,col2,col3,col4=st.columns(4)
    
    with col1:
        st.metric(f"**Total Points Over {date_range} Days:**", value=last_seq_total_points.round(2), delta=f"{total_points_delta} Points ")
        st.metric(f"**Proportion Purchased Over {date_range} Days:**", value=f"{last_seq_prop_purchased:.2f} %", delta=f"{prop_purchased_delta} %")
    with col2:
        st.metric(f"**Total Logins Over {date_range} Days:**", value=last_seq_total_logins, delta=f"{total_logins_delta} Logins")
        st.metric(f"**Average Purchase Amount (USD) Over {date_range} Days:**", value=f"{last_seq_average_purchase_amount:.2f}", delta=f"{average_purchase_amount_delta} $")
    
    with col3:
        st.metric(f"**Total Ads Seen Over {date_range} Days:**", value=last_seq_total_ads, delta = f"{total_ads_delta} Ads")
        st.metric(f"**Average Ad Engagement Time (s) Over {date_range} Days:**", value=f"{last_seq_average_ad_duration:.2f}", delta=f"{average_ad_duration_delta} s")
    with col4:
        st.metric(f"**Total Purchase Over {date_range} Days:**", value=last_seq_total_purchases, delta=f"{total_purchases_delta} Purchases")
        st.metric(f"**Total Purchase Amount (USD) Over {date_range} Days:**", value=f"{last_seq_total_purchase_amount:.2f}", delta=f"{total_purchase_amount_delta} $")

    st.markdown(
        f'<div class="tooltip-text">Metrics from Past {date_range} Days starting from last Login Date. Compares against prior {date_range} Days if any.</div>',
        unsafe_allow_html=True,
    )


# -----------------------------------------------------------------------------------
badge_urls = {
    "VICTORY_ROYALE": "https://github.com/sfc-gh-dyu/PLAYER360_IMAGES/blob/main/images/trophy-cup.png?raw=true",
    "ELIMINATION_MILESTONES": "https://github.com/sfc-gh-dyu/PLAYER360_IMAGES/blob/main/images/death-skull.png?raw=true",
    "SURVIVAL_ACHIEVEMENTS": "https://github.com/sfc-gh-dyu/PLAYER360_IMAGES/blob/main/images/heart-plus.png?raw=true",
    "BUILDING_RESOURCES": "https://github.com/sfc-gh-dyu/PLAYER360_IMAGES/blob/main/images/capitol.png?raw=true",
    "EXPLORATION_TRAVEL": "https://github.com/sfc-gh-dyu/PLAYER360_IMAGES/blob/main/images/journey.png?raw=true",
    "WEAPON_USAGE": "https://github.com/sfc-gh-dyu/PLAYER360_IMAGES/blob/main/images/switch-weapon.png?raw=true",
    "ASSIST_TEAMMATES": "https://github.com/sfc-gh-dyu/PLAYER360_IMAGES/blob/main/images/two-shadows.png?raw=true",
    "EVENT_CHALLENGES": "https://github.com/sfc-gh-dyu/PLAYER360_IMAGES/blob/main/images/black-book.png?raw=true",
    "CREATIVE_MODE": "https://github.com/sfc-gh-dyu/PLAYER360_IMAGES/blob/main/images/cubes.png?raw=true",
    "SOCIAL_ACHIEVEMENTS": "https://github.com/sfc-gh-dyu/PLAYER360_IMAGES/blob/main/images/party-popper.png?raw=true"
}


earned_achievements = achievements_df.iloc[0, 1:].to_dict()
earned_badges = [badge_urls[ach] for ach, earned in earned_achievements.items() if earned]
# Generate badges in a horizontal row
st.markdown("### Achievements Unlocked")
if earned_badges:
    badge_html = "".join(
        f"""
        <figure style="display:inline-block; text-align:center; margin:5px; width:80px;">
            <img src="{badge_urls[ach]}" style="width:50px; height:50px;">
            <figcaption style="font-size:12px; color:lightgray; word-wrap:break-word; overflow-wrap:break-word;">
                {ach.replace('_', ' ').title()}
            </figcaption>
        </figure>
        """
        for ach, earned in earned_achievements.items() if earned
    )
    st.markdown(badge_html + "<br> <br>", unsafe_allow_html=True)
else:
    st.markdown("No achievements earned yet!")

points, support_ticket, purchases, sessions, churn_likelihood = st.tabs(["POINTS",
                                                                         "SUPPORT TICKET",
                                                                         "PURCHASES",
                                                                         "SESSIONS",
                                                                       "CHURN LIKELIHOOD"])

with points:
    player_events_points_df['DAY'] = pd.to_datetime(player_events_points_df['LOG_IN'].dt.date)
    if start_date:
            player_events_points_df= save_filter(player_events_points_df, "LOG_IN", start_date, end_date)
    aggregated_df = player_events_points_df.groupby(['DAY']).agg({
        'DAMAGE_POINTS': 'sum',
        'DISTANCE_POINTS': 'sum',
        'KILLS_POINTS': 'sum',
        'HEADSHOTS_POINTS': 'sum',
        'HEALS_POINTS': 'sum',
        'ASSISTS_POINTS': 'sum',
        'BOOSTS_POINTS': 'sum',
        'WEAPONS_POINTS': 'sum'
    }).reset_index()
    col1, col2 = st.columns(2)
    with col1:
        fig = px.line(
            aggregated_df,
            x='DAY', 
            y=['DAMAGE_POINTS', 'DISTANCE_POINTS', 'KILLS_POINTS', 'HEADSHOTS_POINTS', 
               'HEALS_POINTS', 'ASSISTS_POINTS', 'BOOSTS_POINTS', 'WEAPONS_POINTS'],
            title="Points Over Time per User",
            labels={"DAY": "Date", "value": "Points", "variable": "Point Type"},
            markers=True,
            render_mode='svg'
        )
        st.plotly_chart(fig)
        
    with col2:
        aggregated_user_df = aggregated_df[['DAMAGE_POINTS', 'DISTANCE_POINTS', 'KILLS_POINTS', 
                                                      'HEADSHOTS_POINTS', 'HEALS_POINTS', 'ASSISTS_POINTS', 
                                                      'BOOSTS_POINTS', 'WEAPONS_POINTS']].sum().reset_index()
        aggregated_user_df.columns = ['Point Category', 'Points']
        aggregated_user_df = aggregated_user_df.drop(aggregated_user_df.index[0]).reset_index(drop=True)
        
        fig = px.pie(aggregated_user_df, names='Point Category', values="Points", title=f"Points Breakdown For User {user_id}")
        st.plotly_chart(fig,use_container_width=True)
    

with support_ticket:
    # SUPPORT_TICKETS
    
    user_support_ticket_df = support_ticket_df[support_ticket_df['USER_ID'] == user_id]
    st.markdown("### Support Ticket")
    if len(user_support_ticket_df) == 0:
        st.markdown(f"**HAS SUPPORT TICKET:** FALSE")
    else:
        st.markdown(f"**HAS SUPPORT TICKET:** TRUE")
        st.markdown(f"**CATEGORY:** {user_support_ticket_df['CATEGORY'].values[0]}")
        st.markdown(f"**CASE DESCRIPTION:** {user_support_ticket_df['CASE_DESCRIPTION'].values[0]}")
        st.markdown(f"**SENTIMENT ANALYSIS:** {user_support_ticket_df['SENTIMENT_ANALYSIS'].values[0]}")
        st.markdown(f"**DATE CREATED:** {user_support_ticket_df['DATE_CREATED'].values[0]}")
        # TODO summarize support ticket description
    st.divider()

with purchases:
    # PURCHASES 
   
    purchases_df['DAY'] = pd.to_datetime(purchases_df['TIMESTAMP_OF_PURCHASE'].dt.date)
    purchased_df['DAY'] = pd.to_datetime(purchased_df['TIMESTAMP_OF_PURCHASE'].dt.date)
    if start_date:
        purchases_df = save_filter(purchases_df, 'TIMESTAMP_OF_PURCHASE', start_date, end_date)
        purchased_df = save_filter(purchased_df, 'TIMESTAMP_OF_PURCHASE', start_date, end_date)
    
    # include total_ads seen and total_purchases over time to show behavior over  time
    day_purchases_df = purchases_df.groupby('DAY').agg(
        total_ads=('AD_INTERACTION_ID', 'count'),
        total_ad_engagement_time=('AD_ENGAGEMENT_TIME', 'sum')
    ).reset_index() 
    day_purchased_df = purchased_df.groupby('DAY').agg(
        total_purchase_amount=('PURCHASE_AMOUNT', 'sum'),
        total_purchases = ('PURCHASE_ID', 'count')
    ).reset_index()
    
    col1, col2 = st.columns(2)
    with col1:
        # include player type for analytics breakdown
        purchase_summary = purchases_df.groupby('PURCHASE_TYPE')['PURCHASE_AMOUNT'].sum().reset_index()
        purchase_summary = purchase_summary[purchase_summary['PURCHASE_TYPE'] != 'none']
        fig = px.pie(purchase_summary, 
                 names='PURCHASE_TYPE', 
                 values='PURCHASE_AMOUNT', 
                 title='Purchase Amount by Category')
        st.plotly_chart(fig,use_container_width=True)

        purchase_amount_over_time_df = purchases_df.groupby(['DAY','PURCHASE_TYPE'])['PURCHASE_AMOUNT'].sum().reset_index()
        purchase_amount_over_time_df = purchase_amount_over_time_df[purchase_amount_over_time_df['PURCHASE_TYPE'] != 'none']
        
        fig = px.line(purchase_amount_over_time_df, 
                  x='DAY', 
                  y='PURCHASE_AMOUNT', 
                  color='PURCHASE_TYPE', 
                  title="Purchasing Behavior Over Time by Purchase Category",
                      render_mode='svg')
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        # include ad type for engagement analytics
        purchase_summary = purchases_df.groupby('AD_TYPE')['PURCHASE_AMOUNT'].sum().reset_index()
        fig = px.pie(purchase_summary, 
                 names='AD_TYPE', 
                 values='PURCHASE_AMOUNT', 
                 title='Purchase Amount by AD Type')
        st.plotly_chart(fig,use_container=True)

        purchase_amount_over_time_df = purchases_df.groupby(['DAY','AD_TYPE'])['PURCHASE_AMOUNT'].sum().reset_index()
        fig = px.line(purchase_amount_over_time_df, 
                    x='DAY', 
                    y='PURCHASE_AMOUNT', 
                    color='AD_TYPE', 
                    title="Purchasing Behavior Over Time by AD Type",
                     render_mode='svg')
        st.plotly_chart(fig, use_container_width=True)

    result_df = pd.merge(day_purchases_df, day_purchased_df, on=['DAY'], how='left').fillna(0)
    result_df.columns = [u.upper() for u in result_df.columns]
    st.markdown(f"**Customer Spending Over Time**")
    st.line_chart(result_df, x='DAY', y=['TOTAL_ADS', 'TOTAL_PURCHASE_AMOUNT', 'TOTAL_AD_ENGAGEMENT_TIME', "TOTAL_PURCHASES"])



    st.markdown("### ADS")
    create_pagination(purchases_df, "purchases")


with sessions:
   
    sessions_df["DAY"] = pd.to_datetime(sessions_df["LOG_IN"].dt.date)
    if start_date:
        sessions_df = save_filter(sessions_df, "LOG_IN", start_date, end_date)
    col1, col2 = st.columns(2)
    with col1:
        sessions_summary = sessions_df.groupby('DEVICE_TYPE')['SESSION_DURATION_MINUTES'].sum().reset_index()
        fig = px.pie(sessions_summary, 
                 names='DEVICE_TYPE', 
                 values='SESSION_DURATION_MINUTES', 
                 title='GAMETIME BY DEVICE TYPE')
        st.plotly_chart(fig,use_container_width=True)

    with col2:
        if start_date:
            date_range = pd.date_range(start_date, end_date, freq='D')
        else:
            date_range = pd.date_range(first_login, end_date, freq='D')
        
        day_sessions_df = sessions_df.groupby('DAY').agg(
            total_session_duration=('SESSION_DURATION_MINUTES', 'sum'),
            total_sessions=('SESSION_ID', 'count')
        ).reset_index()
    
        # for each user add in the days they were inactive as 0,0,0
        day_sessions_df['SESSION_INACTIVE'] = 0
        day_sessions_df.columns = [u.upper() for u in list(day_sessions_df.columns)]
        
        # Create a dataframe with all days for this user
        user_days_df = pd.DataFrame({'DAY': date_range})
    
        # Merge with existing day_sessions_df to get the corresponding session data
        day_sessions_df = pd.merge(user_days_df, day_sessions_df, 
                                     on=['DAY'], how='outer')
        
        # Fill missing values with 0
        day_sessions_df['TOTAL_SESSION_DURATION'] = day_sessions_df['TOTAL_SESSION_DURATION'].fillna(0)
        day_sessions_df['TOTAL_SESSIONS'] = day_sessions_df['TOTAL_SESSIONS'].fillna(0)
        day_sessions_df['SESSION_INACTIVE'] = day_sessions_df['SESSION_INACTIVE'].fillna(1)
        
        # Create the plotly figure
        fig = go.Figure()
        
        # Plot Total Sessions (blue line with markers)
        fig.add_trace(go.Scatter(x=day_sessions_df['DAY'], 
                                 y=day_sessions_df['TOTAL_SESSIONS'], 
                                 mode='lines+markers', 
                                 name='Total Sessions', 
                                 line=dict(color='blue'), 
                                 marker=dict(symbol='circle')))
        
        # Plot Total Session Duration (green line with x markers)
        fig.add_trace(go.Scatter(x=day_sessions_df['DAY'], 
                                 y=day_sessions_df['TOTAL_SESSION_DURATION'], 
                                 mode='lines+markers', 
                                 name='Total Session Duration', 
                                 line=dict(color='red'), 
                                 marker=dict(symbol='x')))
        
        # Identify inactive periods
        inactive_mask = day_sessions_df['SESSION_INACTIVE'] == 1

        if start_date:
            start_day = start_date
        else:
            start_day = first_login
        end_day = None
        
        # Add shaded regions for inactivity periods
        for i in range(1, len(day_sessions_df)):
            if inactive_mask[i] and not inactive_mask[i-1]:
                # Start of inactivity
                start_day = day_sessions_df['DAY'].iloc[i]
            elif not inactive_mask[i] and inactive_mask[i-1]:
                # End of inactivity
                end_day = day_sessions_df['DAY'].iloc[i-1]
                fig.add_vrect(x0=start_day, x1=end_day, fillcolor="gray", opacity=0.3, line_width=0)
        
        fig.update_layout(
            title=f'Session Metrics for User {user_id}',
            xaxis_title='Day',
            yaxis_title='Value',
            xaxis_tickangle=45,  
            legend_title="Metrics",
            template="plotly",
        )

       
        st.plotly_chart(fig)

    st.markdown("### SESSIONS")
    create_pagination(sessions_df, "sessions")

def create_rolling_plot(x_col, y_cols, chart_df, title):
    # Create a figure
    fig = go.Figure()

    # Add traces for each y-column
    for i, y_col in enumerate(y_cols):
        
        # Assign y-axis based on the trace index
        yaxis_name = f'y{i+1}' if i > 0 else 'y'
        
        # Add the trace to the figure
        fig.add_trace(go.Scatter(
            x=chart_df[x_col], 
            y=chart_df[y_col],
            mode='lines+markers',
            name=y_col,
            yaxis=yaxis_name,
        ))

    # Update layout for multiple y-axes
    layout = {
        'title': title,
        'xaxis': {'title': x_col},
        'yaxis': {
            'titlefont': dict(color='lightblue'),
            'tickfont': dict(color='lightblue')
        }
    }

    # Add secondary and tertiary y-axes dynamically
    for i in range(1, len(y_cols)):
        layout[f'yaxis{i+1}'] = {
            'overlaying': 'y',  # Share the x-axis
            'side': 'right' if i %2 == 1 else 'left',  # Place right for second axis, left for others
            'titlefont': dict(color='blue' if i == 1 else 'pink' if i == 2 else 'red'),
            'tickfont': dict(color='blue' if i == 1 else 'pink' if i == 2 else 'red')
        }
    
    fig.update_layout(layout)

    return fig

with churn_likelihood:
    # ML Model
    if st.session_state.active_user == 0:
        features_df = load_query(f"SELECT * FROM {session.get_current_database()}.APP.ROLLING_CHURN_FEATURES WHERE USER_ID = {user_id}")
        features_df['DAY'] = pd.to_datetime(features_df['DAY'])
        features_df = features_df[features_df['DAY'] >= start_date]
        chart_df = features_df
    else:
        features_df = load_query(f"SELECT * FROM {session.get_current_database()}.APP.TO_BE_PREDICTED_CHURN_FEATURES WHERE USER_ID = {user_id}")
        chart_df = load_query(f"SELECT * FROM {session.get_current_database()}.APP.ROLLING_CHURN_FEATURES WHERE USER_ID = {user_id}")
        chart_df['DAY'] = pd.to_datetime(chart_df['DAY'])
        chart_df = chart_df[chart_df['DAY'] >= start_date]
    
    Features_label = [
    "TOTAL_SESSION_DURATION_ROLLING_30_DAYS",
    "TOTAL_SESSIONS_ROLLING_30_DAYS",
    "AVERAGE_SESSION_LEN_ROLLING_30_DAYS",
    "TOTAL_POINTS_ROLLING_30_DAYS",
    "AVERAGE_POINTS_PER_SESSION_ROLLING_30_DAYS",
    "TOTAL_PURCHASE_AMOUNT_ROLLING_30_DAYS",
    "TOTAL_PURCHASES_ROLLING_30_DAYS",
    "AVG_PURCHASE_AMOUNT_ROLLING_30_DAYS",
    "TOTAL_ADS_ROLLING_30_DAYS",
    "AD_CONVERSION_RATE_ROLLING_30_DAYS",
    "TOTAL_AD_ENGAGEMENT_TIME_ROLLING_30_DAYS",
    "AVERAGE_ENGAGEMENT_TIME_ROLLING_30_DAYS"
    ]

    X_test = features_df[Features_label]

    reg = Registry(session=session)

    MODEL_NAME = "Player360_RollingChurn_Classifier"
    MODEL_VERSION = "v1"
    
    
    mv= cache_model(MODEL_NAME, MODEL_VERSION)
    mv_prediction = mv.run(X_test, function_name="predict_proba")
    prediction_value = mv_prediction['PREDICT_PROBA_1'].values[0]
    if prediction_value >= .5:
        st.markdown(f"""
            <div style="padding: 10px; border-radius: 5px; background-color: #f8d7da; color: #721c24; font-size: 18px; font-weight: bold;">
                🚨 <strong>Predicted Churn Likelihood:</strong> <span style="color: #d63384;">{prediction_value:.2f}</span>
            </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="padding: 10px; border-radius: 5px; background-color: #d4edda; color: #155724; font-size: 18px; font-weight: bold;">
            ✅ <strong>Predicted Churn Likelihood:</strong> <span style="color: #28a745;">{prediction_value:.2f}</span>
        </div>
        """, unsafe_allow_html=True)        

    with st.form("Shap_form"):
        sample_size = st.slider(label="Select Sampling Size",
                                    min_value = 0,
                                    max_value = len(chart_df),
                                    value = 1)
        selected_plot_type = st.selectbox(label='Select a summary plot type', \
                                          options=['dot', 'bar', 'violin'])
        submitted = st.form_submit_button("Get Global Shap")
        if submitted:
            sample_df = chart_df[Features_label]
            mv_explanations = mv.run(sample_df[:sample_size], function_name="explain")
            mv_explanations.columns = [u.replace("_explanation", "").strip('""') for u in mv_explanations.columns]
            
            def render_shap_plot():
                plt.figure(figsize=(8, 4))
                shap.summary_plot(-mv_explanations.values, sample_df[:sample_size], show=False, plot_type = selected_plot_type)
                buf = io.BytesIO()
                plt.tight_layout()
                plt.savefig(buf, format='png')
                buf.seek(0)
                return buf
            st.subheader("SHAP Summary Plot")
            buf = render_shap_plot()
            st.image(buf, caption='SHAP Summary Plot', use_column_width=True)

    col1, col2 = st.columns(2)
    with col1:

        st.plotly_chart(create_rolling_plot('DAY', ["TOTAL_SESSION_DURATION_ROLLING_30_DAYS", \
                                                            "TOTAL_SESSIONS_ROLLING_30_DAYS", \
                                                            "AVERAGE_SESSION_LEN_ROLLING_30_DAYS"], chart_df, 
                                                     'Rolling 30 Day Sessions Features Over Time'), 
                        use_container_width=True)

        fig = px.line(
            data_frame=chart_df,
            x='DAY', 
            y=[ "TOTAL_PURCHASE_AMOUNT_ROLLING_30_DAYS",
                "TOTAL_PURCHASES_ROLLING_30_DAYS",
                "AVG_PURCHASE_AMOUNT_ROLLING_30_DAYS",],
            title="Rolling 30 Day Purchases Features Over Time",
            labels={"DAY": "Date", "value": "Points", "variable": "Feature"},
            markers=True,
            render_mode='svg'
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.plotly_chart(create_rolling_plot('DAY', 
                                                     ["TOTAL_POINTS_ROLLING_30_DAYS","AVERAGE_POINTS_PER_SESSION_ROLLING_30_DAYS"], 
                                                     chart_df,
                                            'Rolling 30 Day Points Features Over Time'), 
                        use_container_width=True)
        st.plotly_chart(create_rolling_plot('DAY', 
                                                     ["TOTAL_ADS_ROLLING_30_DAYS",
                                                    "AD_CONVERSION_RATE_ROLLING_30_DAYS",
                                                    "TOTAL_AD_ENGAGEMENT_TIME_ROLLING_30_DAYS",
                                                    "AVERAGE_ENGAGEMENT_TIME_ROLLING_30_DAYS"], 
                                                     chart_df,
                                                    'Rolling 30 Day Ads Features Over Time'), 
                        use_container_width=True)