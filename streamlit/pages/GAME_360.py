# Import python packages
import streamlit as st
from snowflake.snowpark.context import get_active_session
from snowflake.ml.registry import Registry
import streamlit.components.v1 as components
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import plotly.graph_objects as go
import shap
import altair as alt
import io
import shap
from ydata_profiling import ProfileReport
from streamlit_extras.stylable_container import stylable_container
from datetime import datetime
from snowflake.ml.modeling.preprocessing import OrdinalEncoder


st.set_page_config(layout="wide")
st.title("GAME 360")
st.divider()
session = get_active_session()

age_ranges_dict = {
    '0-11': (0,11),
    '12-17': (12, 17),
    '18-24': (18, 24),
    '25-34': (25, 34),
    '35-44': (35, 44),
    '45-54': (45, 54),
    '55-64': (55, 64),
    '65+': (65, 100) 
}



@st.cache_data(show_spinner=False)
def load_query(query):
    query = session.sql(query).to_pandas()
    return query
    
@st.cache_data(show_spinner=False)
def load_table(table_name):
    table = session.table(table_name).to_pandas()
    return table
    
@st.cache_data(show_spinner=False)
def save_eda(df):
    html = ProfileReport(eda_df).to_html()
    return html

@st.cache_data(show_spinner=False)
def split_frame(input_df, rows):
    df = [input_df.loc[i : i + rows - 1, :] for i in range(0, len(input_df), rows)]
    return df
    
def cache_model(model_name, version, load=False):
    mv= reg.get_model(model_name).version(version)
    if load:
        mv = mv.load(force=True)
    return mv

@st.cache_data(show_spinner=False)
def filter_dataframe(df, playerbase, age_range, gender, country_range,player_type, support_ticket, rank_range):
    # filter by playerbase_ranges
    if playerbase == "Active":
        df = df[df['CHURNED'] == 0]
    elif playerbase == 'Inactive':
        df = df[df['CHURNED'] == 1]

    # filter by age_range
    if age_ranges:
        selected_age_filters = [
            (age_ranges_dict[range][0], age_ranges_dict[range][1]) for range in age_ranges
        ]
        
        # Apply the filter
        df = df[
            df['AGE'].apply(
                lambda x: any(lower <= x <= upper for lower, upper in selected_age_filters)
            )
        ]

    # filter by gender
    if gender == "Male":
        df = df[df['GENDER'] == 'Male']
    elif gender == 'Female':
        df = df[df['GENDER'] == 'Female']

    # filter by country
    if country_ranges:
        df = df[df['LOCATION'].isin(country_ranges)]

    # filter by player type
    if player_type == 'Hardcore':
        df = df[df['PLAYER_TYPE'] == 'Hardcore']
    elif player_type == 'Casual':
        df = df[df['PLAYER_TYPE'] == 'Casual']

    # filter by support ticket
    if support_ticket == "Yes":
        df = df[df['HAS_SUPPORT_TICKET'] == True]
    elif support_ticket == "No":
        df = df[df['HAS_SUPPORT_TICKET'] == False]

    if rank_range:
        df = df[df['RANK_NAME'].isin(rank_range)]
    
    return df

@st.cache_data(show_spinner=False)
def preprocess_filtered_dataframe(filtered_df):
    filtered_df['AGE_GROUP'] = pd.cut(filtered_df['AGE'], bins=[0,12,18, 24, 34, 44, 54, 64, 100], labels=['0_11','12_17','18_24', '25_34', '35_44', '45_54', '55_64', '65+'])
    categories = {"RANK_NAME":["Bronze", "Silver", "Gold", "Platinum", "Diamond", "Elite", "Champion", "Unreal"],
         "PLAYER_TYPE":["Casual", "Hardcore"],
         "GENDER":["Female", "Male"]} 
    snowml_oe = OrdinalEncoder(input_cols=["RANK_NAME", "PLAYER_TYPE", "GENDER"], output_cols=["RANK_NAME_OE", "PLAYER_TYPE_OE", "GENDER_OE"], categories=categories)
    encoded_feature_df = snowml_oe.fit(filtered_df).transform(filtered_df)
    return encoded_feature_df

def create_saved_pagination(dataset :pd.DataFrame, key :str):
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
        if st.button("Save to Snowflake"):
           with st.spinner('Saving to Snowflake...'):
                # Real Snowflake operation
                session.write_pandas(df=filtered_df, 
                                     table_name="FILTERED_DF", 
                                     database=f"{session.get_current_database()}", 
                                     schema="APP", 
                                     quote_identifiers=False,
                                     auto_create_table=True,
                                     overwrite=True)
                st.success("Data saved successfully!")
            
    pages = split_frame(dataset, batch_size)
    pagination.dataframe(data=pages[current_page - 1], use_container_width=True)

class AltairCharts():
    def __init__(self):
        return None

    def plot_daily_monthly_breakdown(self,x_col, y_col, df, daily_title, monthly_title, x_cols=None,y_cols=None, dfs=None,titles=None, override=False):
        selected_month = alt.selection_interval(encodings=["x"], empty="all")

        if override:
            agg = 'average'
        else:
            agg = 'sum'
        
        monthly_base = alt.Chart(df).mark_line().encode(
            x=alt.X(x_col, type='temporal', timeUnit='yearmonth', title=x_col),
            y=alt.Y(y_col, type='quantitative', aggregate='sum', title=y_col)
        ).add_selection(selected_month).properties(
            title=monthly_title
        )
        daily_base = alt.Chart(df).mark_line().encode(
            x=alt.X(x_col, type='temporal', timeUnit='yearmonthdate', title=x_col),
            y=alt.Y(y_col, type='quantitative', aggregate=agg, title=y_col)
        ).transform_filter(selected_month).properties(
            title=daily_title
        )
        other_charts = []
        if y_cols and dfs and titles:
            if len(y_cols) != len(dfs) or len(dfs) != len(titles):
                raise IllegalArgumentException("Uneven number of y_cols, dfs, and titles passed")
    
            for i,y_col in enumerate(y_cols):
                chart = alt.Chart(dfs[i]).mark_line().encode(
                    x = alt.X(x_cols[i], type='temporal', timeUnit='yearmonthdate', title=x_col),
                    y = alt.Y(y_col, type='quantitative', title=y_col)
                ).transform_filter(selected_month).properties(
                    title=titles[i]
                )
                other_charts.append(chart)
            
        return monthly_base, daily_base, other_charts
    

# load the dataframes
dau_df = load_query(f"SELECT * FROM {session.get_current_database()}.ANALYTIC.DAILY_ACTIVE_USERS ORDER BY ACTIVE_DATE ASC")
mau_df = load_query(f"""SELECT 
                            TO_DATE(ACTIVE_MONTH) as ACTIVE_MONTH, 
                            ACTIVE_USER_COUNT,
                        FROM {session.get_current_database()}.ANALYTIC.MONTHLY_ACTIVE_USERS ORDER BY ACTIVE_MONTH ASC""")
dcr_df = load_query(f"SELECT LOG_IN_DATE AS DATE, CHURNED_USERS, ACTIVE_USERS, CHURN_RATE_PERCENTAGE FROM {session.get_current_database()}.ANALYTIC.DAILY_CHURN_RATE ORDER BY DATE ASC")
mcr_df = load_query(f"SELECT DATE_FROM_PARTS(year, month, 1) AS DATE, CHURNED_USERS, ACTIVE_USERS, CHURN_RATE_PERCENTAGE FROM {session.get_current_database()}.ANALYTIC.MONTHLY_CHURN_RATE ORDER BY DATE ASC")
arpdau_df = load_query(f"SELECT * FROM {session.get_current_database()}.ANALYTIC.ARPDAU ORDER BY ACTIVE_DATE ASC")
darppu_df = load_query(f"SELECT * FROM {session.get_current_database()}.ANALYTIC.DARPPU ORDER BY ACTIVE_DATE ASC")
cltv_cohort_df = load_query(f"SELECT * FROM {session.get_current_database()}.ANALYTIC.COHORT_CLTV ORDER BY TO_DATE(COHORT_MONTH || '-01', 'YYYY-MM-DD') ASC")
ad_conversion_df = load_query(f"SELECT * FROM {session.get_current_database()}.ANALYTIC.AD_CONVERSION_OVER_TIME ORDER BY MONTH ASC")
features_df = load_query(f"SELECT * FROM {session.get_current_database()}.APP.ROLLING_CHURN_FEATURES")
eda_df = load_query(f"""SELECT 
                        r.user_id, 
                        r.total_logins,
                        r.logged_in_after_1_day,
                        r.logged_in_after_7_days,
                        r.logged_in_after_30_days,
                        r.logged_in_in_last_30_days,
                        r.days_since_last_login,
                        d.age,
                        d.gender,
                        d.location,
                        d.average_sessions_per_active_week,
                        d.average_session_duration,
                        d.player_type,
                        d.total_ads,
                        d.avg_purchase_amount_per_ad,
                        d.has_support_ticket,
                        ur.total_points,
                        ur.rank_name,
                        ( 
                                CASE WHEN VICTORY_ROYALE THEN 1 ELSE 0 END +
                                CASE WHEN ELIMINATION_MILESTONES THEN 1 ELSE 0 END +
                                CASE WHEN SURVIVAL_ACHIEVEMENTS THEN 1 ELSE 0 END +
                                CASE WHEN BUILDING_RESOURCES THEN 1 ELSE 0 END +
                                CASE WHEN EXPLORATION_TRAVEL THEN 1 ELSE 0 END +
                                CASE WHEN WEAPON_USAGE THEN 1 ELSE 0 END +
                                CASE WHEN ASSIST_TEAMMATES THEN 1 ELSE 0 END +
                                CASE WHEN EVENT_CHALLENGES THEN 1 ELSE 0 END +
                                CASE WHEN CREATIVE_MODE THEN 1 ELSE 0 END +
                                CASE WHEN SOCIAL_ACHIEVEMENTS THEN 1 ELSE 0 END
                            ) / 11.0 AS ACHIEVEMENTS_PERCENTAGE,
                        ae.total_purchases,
                        ae.proportion_purchased,
                        ae.average_purchase_amount,
                        ae.average_ad_engagement_time,
                        r.churned
                        FROM {session.get_current_database()}.ANALYTIC.RETENTION r 
                        JOIN {session.get_current_database()}.ANALYTIC.DEMOGRAPHICS d ON r.user_id = d.user_id 
                        JOIN {session.get_current_database()}.ANALYTIC.USER_RANKINGS ur ON r.user_id = ur.user_id
                        JOIN {session.get_current_database()}.RAW.ACHIEVEMENTS a ON r.user_id = a.user_id
                        JOIN {session.get_current_database()}.ANALYTIC.AD_ENGAGEMENT ae ON r.user_id = ae.user_id
                        """)

components.html("""
  <script>
    window.parent.document.querySelector('[data-testid="stSidebar"]').style.width = "25%";
  </script>
""", height=0)
st.markdown(
    """
    <style>
        [data-testid=stSidebarUserContent] {
            padding-top: 3.5rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    date_range = st.select_slider(label='Date Range', options=[30, 60, 90, 365, 'Lifetime'])
    st.divider()
    playerbase = st.selectbox(label='Playerbase',options=['All','Active', 'Inactive'])
    support_ticket = st.selectbox(label='Has Support Ticket', options=['All','Yes', 'No'])
    age_ranges = st.multiselect(label='Age Range', options=['0-11','12-17','18-24', '25-34', '35-44', '45-54', '55-64', '65+'])
    gender = st.selectbox(label='Gender', options=['All','Male', 'Female'])
    country_ranges = st.multiselect(label='Country', options=['China', 'Mexico', 'UK', 'USA', 'Canada', 'Brazil', 'France', 'Germany', 
                                                             'Korea', 'Poland'])
    player_type = st.selectbox(label='Player Type', options=['All','Hardcore', 'Casual', ])
    rank_range = st.multiselect(label="Ranks", options=['Bronze', 'Silver', 'Gold', 'Platinum', 'Champion', 'Unreal', 'Elite', 'Diamond'])
    
    #cohort_ranges = st.multiselect(label='Join Month', options=['TOOD'])
    #platform_type = st.multiselect(label='Platform Type', options=['TODO'])

# then for the game metrics, show the dates breakdown
current_date = datetime.now() - pd.Timedelta(days=7)
if date_range != "Lifetime":
    start_date = current_date - pd.Timedelta(days=date_range)
    if date_range == 30:
        ranges = (30, 1)
    elif date_range == 60:
        ranges = (60,2)
    elif date_range == 90:
        ranges = (90,3)
    elif date_range == 365:
        ranges = (365, 52)
    else:
        # return random placeholder
        ranges = ("Lifetime","Lifetime")
else:
    start_date = None
    # return random placeholder
    ranges = ("Lifetime","Lifetime")

def calculate_metrics(df, index, col_name):

    if start_date:
        last_seq_df = df.iloc[-index:][col_name].mean()
        prev_seq_df = df.iloc[-2*index:-index][col_name].mean()
        delta = last_seq_df - prev_seq_df
        return last_seq_df, delta.round(2)
    else:
        return df[col_name].mean(), "~"

# find total ad_conversion per month
monthly_conversion_df = ad_conversion_df.groupby('MONTH').agg(
    TOTAL_ADS=('TOTAL_ADS', 'sum'),
    PURCHASED_ADS=('PURCHASED_ADS', 'sum')
).reset_index()
monthly_conversion_df['AD_CONVERSION_RATE'] = monthly_conversion_df['PURCHASED_ADS'] / monthly_conversion_df['TOTAL_ADS'] * 100
monthly_conversion_df['AD_CONVERSION_RATE'] = monthly_conversion_df['AD_CONVERSION_RATE'].fillna(0)


last_seq_average_dau, average_dau_delta = calculate_metrics(dau_df, ranges[0], 'ACTIVE_USER_COUNT')

last_seq_average_mau, average_mau_delta = calculate_metrics(mau_df, ranges[1], 'ACTIVE_USER_COUNT')

last_seq_average_dcr, average_dcr_delta = calculate_metrics(dcr_df, ranges[0], 'CHURN_RATE_PERCENTAGE')

last_seq_average_mcr, average_mcr_delta = calculate_metrics(mcr_df, ranges[1], 'CHURN_RATE_PERCENTAGE')

last_seq_average_arpdau, average_arpdau_delta = calculate_metrics(arpdau_df, ranges[0], 'ARP_DAU')

last_seq_average_darppu, average_darppu_delta = calculate_metrics(darppu_df, ranges[0], 'DARPPU')

last_seq_average_conversion_rate, average_conversion_rate_delta = calculate_metrics(monthly_conversion_df, ranges[1], 'AD_CONVERSION_RATE')

last_seq_average_cltv, average_cltv_delta = calculate_metrics(cltv_cohort_df, ranges[1], 'NORMALIZED_LTV')

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
    with st.container(border=True):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric(f"Daily Active Users Over {ranges[0]} Days", value=f"{last_seq_average_dau:.2f}", delta=f"{average_dau_delta} Users" )
            st.metric(
                f"Average Revenue Per Daily Active User Over {ranges[0]} Days",
                value=f"$ {last_seq_average_arpdau:.2f}",
                delta=f"{average_arpdau_delta} $ Change",
            )
        
        with col2:
            st.metric(f"Monthly Active Users Over {ranges[1]} Months", value=f"{last_seq_average_mau:.2f}", delta=f"{average_mau_delta:} Users")
            st.metric(
                f"Daily Average Revenue Per Paying User Over {ranges[0]} Days",
                value=f"$ {last_seq_average_darppu:.2f}",
                delta=f"{average_darppu_delta} $ Change",
            )
        
        with col3:
            st.metric(
                f"Daily Churn Rate Over {ranges[0]} Days",
                value=f"{last_seq_average_dcr:.2f} %",
                delta=f"{average_dcr_delta} % Change",
                delta_color="inverse"
            )
            
            st.metric(
                f"Ad Conversion Rate Over {ranges[1]} Months",
                value=f"{last_seq_average_conversion_rate:.2f} %",
                delta=f"{average_conversion_rate_delta} % Change"
            )
            
        with col4:
            st.metric(
                f"Monthly Churn Rate Over {ranges[1]} Months",
                value=f"{last_seq_average_mcr:.2f} %",
                delta=f"{average_mcr_delta} % Change",
                delta_color="inverse"
            )
            
            st.metric(
                f"Customer Lifetime Value by Cohort Over {ranges[1]} Months",
                value=f"$ {last_seq_average_cltv:.2f}",
                delta=f"{average_cltv_delta} $ Change"
            )
            
        st.markdown(
            f'<div class="tooltip-text"> Daily/Monthly Metrics Averaged from Past {date_range} Days starting from Current Day. Compares against prior {date_range} Day Averages if any.</div>',
            unsafe_allow_html=True,
        )

# implement filtering
filtered_df = filter_dataframe(eda_df, playerbase, age_ranges, gender, country_ranges, player_type, support_ticket, rank_range)    


st.markdown("### Filtered Dataframe")
create_saved_pagination(filtered_df, "Filtered_Dataframe")
st.markdown("<br><br>", unsafe_allow_html=True)


static_demographics, static_game_metrics, dynamic_demographics, dynamic_churn_likelihood = st.tabs(
    ["STATIC DEMOGRAPHICS",
    "STATIC GAME METRICS",
    "DYNAMIC DEMOGRAPHICS",
   "DYNAMIC CHURN LIKELIHOOD"])

# annotations on heatmap
show_annotations = st.sidebar.checkbox("Show Annotations", value=False)

with static_demographics:
    # use Profile Report to summarize EDA
    components.html(save_eda(eda_df), height=500, scrolling=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        eda_df['Age_Group'] = pd.cut(eda_df['AGE'], bins=[0,12,18, 24, 34, 44, 54, 64, 100], labels=['0_11','12_17','18_24', '25_34', '35_44', '45_54', '55_64', '65+'])
        churn_by_age = eda_df.groupby('Age_Group')['CHURNED'].mean() * 100
        churn_by_age.plot(kind='bar', title="Churn Rate by Age Group")
        plt.ylabel("Churn Rate (%)")
        st.pyplot(plt,clear_figure=True)

    with col2:
        churn_by_location = eda_df.groupby('LOCATION')['CHURNED'].mean() * 100
        churn_by_location.plot(kind='bar', title="Churn Rate by Location")
        plt.ylabel("Churn Rate (%)")
        plt.show()
        st.pyplot(plt,clear_figure=True)

    with col3:
        churn_by_player_type = eda_df.groupby('PLAYER_TYPE')['CHURNED'].mean() * 100
        churn_by_player_type.plot(kind='bar', title="Churn Rate by Player Type")
        plt.ylabel("Churn Rate (%)")
        st.pyplot(plt,clear_figure=True)
            
    col1, col2 = st.columns(2)
    with col1:
        # features-metrics
        sns.heatmap(eda_df[list(eda_df.describe())].corr(), annot=show_annotations, cmap='coolwarm', fmt='.2f', linewidths=0.5, annot_kws={"size": 8})
        plt.title("Correlation Matrix")
        plt.xticks(fontsize=6)  # Set font size for x-axis ticks (feature names)
        plt.yticks(fontsize=6) 
        st.pyplot(plt,clear_figure=True)
        
    with col2:
        sns.pairplot(eda_df[['PROPORTION_PURCHASED', 'AVERAGE_PURCHASE_AMOUNT','AVERAGE_AD_ENGAGEMENT_TIME', 'CHURNED']], diag_kind='kde', hue="CHURNED",palette='husl')
        plt.suptitle('Pair Plot of Purchases and Ad Engagement Information by Churn', y=1.02, fontsize=20)
        plt.tight_layout()
        plt.show()
        st.pyplot(plt,clear_figure=True)
        
    churned_data = eda_df[eda_df["CHURNED"] == 1]
    non_churned_data = eda_df[eda_df["CHURNED"] == 0]
    
    fig = go.Figure()
    
    # Add churned data points (red 'x')
    fig.add_trace(go.Scatter3d(
        x=churned_data["TOTAL_LOGINS"],
        y=churned_data["TOTAL_POINTS"],
        z=churned_data["TOTAL_PURCHASES"],
        mode='markers',
        marker=dict(size=6, color='red', symbol='x'),
        name='Churned'
    ))
    
    # Add non-churned data points (blue markers)
    fig.add_trace(go.Scatter3d(
        x=non_churned_data["TOTAL_LOGINS"],
        y=non_churned_data["TOTAL_POINTS"],
        z=non_churned_data["TOTAL_PURCHASES"],
        mode='markers',
        marker=dict(size=6, color='blue'),
        name='Non-Churned'
    ))
    
    # Set axis labels and title
    fig.update_layout(
        title='Interactive 3D Plot of Total Logins, Total Points, and Total Purchases',
        scene=dict(
            xaxis_title='Total Logins',
            yaxis_title='Total Points',
            zaxis_title='Total Purchases'
        ),
        legend=dict(x=0.1, y=0.9)
    )
    st.plotly_chart(fig, use_container_width=True)

with static_game_metrics:
    col1, col2 = st.columns(2)
    with col1:
        monthly_base, daily_base, other_charts = AltairCharts().plot_daily_monthly_breakdown("ACTIVE_DATE", "ACTIVE_USER_COUNT", dau_df, "Daily Active Users", "Monthly Active Users",
                                                                                             ['ACTIVE_DATE', 'ACTIVE_DATE'],
                                                                                             ["ARP_DAU", "DARPPU"],
                                                                                             [arpdau_df, darppu_df],
                                                                                            ['Average Revenue Per Daily Active User', 'Daily Average Revenue Per Paying Customer'])
        st.altair_chart(alt.vconcat(monthly_base, daily_base, *other_charts), use_container_width=True)
    with col2:
        monthly_base, daily_base, other_charts= AltairCharts().plot_daily_monthly_breakdown("DATE", "CHURNED_USERS", dcr_df, "Daily Churned Users", "Monthly Churned Users")
        st.altair_chart(alt.vconcat(monthly_base, daily_base, *other_charts), use_container_width=True)
        monthly_base, daily_base, _ = AltairCharts().plot_daily_monthly_breakdown("DATE", "CHURN_RATE_PERCENTAGE", dcr_df, "Daily Churned Rate", "Monthly Churned Rate", override=True)
        st.altair_chart(alt.vconcat(monthly_base,daily_base), use_container_width=True)


    st.markdown("**Customer Lifetime Value by Cohort**")
    st.line_chart(cltv_cohort_df, x='COHORT_MONTH', y=['TOTAL_PLAYERS','NORMALIZED_LTV'])

# model explanations
with dynamic_demographics:
    components.html(save_eda(filtered_df), height=500, scrolling=True)
    col1, col2 = st.columns(2)
    with col1:
        # features-metrics
        sns.heatmap(filtered_df[list(filtered_df.describe())].corr(), annot=show_annotations, cmap='coolwarm', fmt='.2f', linewidths=0.5, annot_kws={"size": 8})
        plt.title("Correlation Matrix")
        plt.xticks(fontsize=6)  # Set font size for x-axis ticks (feature names)
        plt.yticks(fontsize=6) 
        st.pyplot(plt,clear_figure=True)
        
    with col2:
        sns.pairplot(filtered_df[['PROPORTION_PURCHASED', 'AVERAGE_PURCHASE_AMOUNT','AVERAGE_AD_ENGAGEMENT_TIME', 'CHURNED']], diag_kind='kde', hue="CHURNED",palette='husl')
        plt.suptitle('Pair Plot of Purchases and Ad Engagement Information by Churn', y=1.02, fontsize=20)
        plt.tight_layout()
        plt.show()
        st.pyplot(plt,clear_figure=True)
    
    

with dynamic_churn_likelihood:

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Rolling Churn Predictor")
        # rolling model explanations
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
        
        reg = Registry(session=session)
        
        MODEL_NAME = "Player360_RollingChurn_Classifier"
        MODEL_VERSION = "v1"

        # filter out the subset
        filtered_features_df = pd.merge(features_df, filtered_df[['USER_ID']], on='USER_ID', how='inner')
        
        mv= cache_model(MODEL_NAME, MODEL_VERSION)
        
        with st.form("Shap_form"):
            sample_size = st.slider(label="Select Sampling Size",
                                        min_value = 0,
                                        max_value = min(len(filtered_features_df), 100000),
                                        value = 1)
            selected_plot_type = st.selectbox(label='Select a summary plot type', \
                                              options=['dot', 'bar', 'violin'])
            submitted = st.form_submit_button("Get Global Shap")
            if submitted:
                sample_df = filtered_features_df[Features_label]
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
                
    with col2:
        st.subheader("Churn Classifier")
        reg = Registry(session=session)

        train_df = preprocess_filtered_dataframe(filtered_df)
        
        MODEL_NAME = "Player360_Churn_Classifier"
        MODEL_VERSION = "v1"
        mv= cache_model(MODEL_NAME, MODEL_VERSION, load=True)

        with st.form("Shap_form2"):
            sample_size = st.slider(label="Select Sampling Size",
                                        min_value = 0,
                                        max_value = min(len(train_df), 100000),
                                        value = 1)
            selected_plot_type = st.selectbox(label='Select a summary plot type', \
                                              options=['dot', 'bar', 'violin'])
            submitted = st.form_submit_button("Get Global Shap")
            if submitted:
                sample_df = train_df[['AGE_GROUP', 'LOCATION', 'AVERAGE_SESSIONS_PER_ACTIVE_WEEK',
       'AVERAGE_SESSION_DURATION', 'HAS_SUPPORT_TICKET',
       'ACHIEVEMENTS_PERCENTAGE', 'PROPORTION_PURCHASED',
       'AVERAGE_PURCHASE_AMOUNT', 'AVERAGE_AD_ENGAGEMENT_TIME', 'RANK_NAME_OE',
       'PLAYER_TYPE_OE', 'GENDER_OE']]
                sample_df["AGE_GROUP"] = pd.Categorical(sample_df["AGE_GROUP"], ordered=False)
                sample_df["LOCATION"] = pd.Categorical(sample_df["LOCATION"])
                sample_df['AGE_GROUP'] = sample_df['AGE_GROUP'].cat.codes
                sample_df['LOCATION'] = sample_df['LOCATION'].cat.codes
                sample_df['HAS_SUPPORT_TICKET'] = sample_df['HAS_SUPPORT_TICKET'].astype(int)
                
                def render_shap_plot():
                    plt.figure(figsize=(8, 4))
                    explainer = shap.TreeExplainer(mv)

                    # Calculate SHAP values
                    shap_values = explainer(sample_df)
                    
                    # Plot SHAP values
                    shap.summary_plot(shap_values, sample_df, show=False, plot_type=selected_plot_type) 
                    buf = io.BytesIO()
                    plt.tight_layout()
                    plt.savefig(buf, format='png')
                    buf.seek(0)
                    return buf
                st.subheader("SHAP Summary Plot")
                buf = render_shap_plot()
                st.image(buf, caption='SHAP Summary Plot', use_column_width=True)