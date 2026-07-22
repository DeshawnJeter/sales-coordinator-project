"""Weekly sales summary generator.

Builds the full report: category/region/store breakdowns compared to a prior
period, discount tracking with margin impact, underperformer flags, and a
short plain-language summary paragraph. Defaults to "this week vs. last
week" but every function accepts explicit (start, end) periods, so any two
periods can be compared.

A "period" is a (start_date, end_date) pair of pandas Timestamps, inclusive
on both ends.
"""

import pandas as pd

DEFAULT_DECLINE_THRESHOLD = 0.10   # underperformer flag: >10% sales decline vs prior period
MARGIN_DECLINE_THRESHOLD = 0.15    # discount flag: >15% relative margin decline vs typical
TOP_DISCOUNTED_COUNT = 10


def prepare_dataframe(df):
    """Parse dates and attach a week_start column. Call once on the combined dataset."""
    df = df.copy()
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date'])
    for col in ('sales', 'discount', 'profit'):
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    weekday = df['date'].dt.weekday
    df['week_start'] = (df['date'] - pd.to_timedelta(weekday, unit='D')).dt.normalize()
    return df


def week_range_for(date):
    """Return the (Monday, Sunday) period containing the given date."""
    date = pd.Timestamp(date).normalize()
    monday = date - pd.Timedelta(days=date.weekday())
    sunday = monday + pd.Timedelta(days=6)
    return monday, sunday


def default_periods(df):
    """Most recent week present in the data, and the calendar week before it."""
    latest_date = df['date'].max()
    current_start, current_end = week_range_for(latest_date)
    prior_start = current_start - pd.Timedelta(days=7)
    prior_end = current_end - pd.Timedelta(days=7)
    return (current_start, current_end), (prior_start, prior_end)


def filter_period(df, period):
    start, end = period
    return df[(df['date'] >= start) & (df['date'] <= end)]


def _pct_change(current, prior):
    if prior == 0:
        return None if current == 0 else 1.0 if current > 0 else -1.0
    return (current - prior) / abs(prior)


def _grouped_comparison(current_df, prior_df, group_col, has_prior_data):
    current_totals = current_df.groupby(group_col).agg(
        sales=('sales', 'sum'), profit=('profit', 'sum'), orders=('sales', 'size')
    )
    prior_totals = prior_df.groupby(group_col).agg(sales=('sales', 'sum'), profit=('profit', 'sum'))

    all_keys = sorted(set(current_totals.index) | set(prior_totals.index))
    rows = []
    for key in all_keys:
        cur_sales = float(current_totals['sales'].get(key, 0.0))
        cur_profit = float(current_totals['profit'].get(key, 0.0))
        cur_orders = int(current_totals['orders'].get(key, 0))
        prior_sales = float(prior_totals['sales'].get(key, 0.0))
        prior_profit = float(prior_totals['profit'].get(key, 0.0))
        had_prior = has_prior_data and key in prior_totals.index

        rows.append({
            'name': key,
            'sales': cur_sales,
            'profit': cur_profit,
            'orders': cur_orders,
            'prior_sales': prior_sales,
            'sales_change': _pct_change(cur_sales, prior_sales) if had_prior else None,
            'sales_change_abs': (cur_sales - prior_sales) if had_prior else None,
        })
    rows.sort(key=lambda r: r['sales'], reverse=True)
    return rows


def category_summary(current_df, prior_df, has_prior_data):
    return _grouped_comparison(current_df, prior_df, 'category', has_prior_data)


def region_summary(current_df, prior_df, has_prior_data):
    return _grouped_comparison(current_df, prior_df, 'region', has_prior_data)


def store_summary(current_df, prior_df, has_prior_data):
    return _grouped_comparison(current_df, prior_df, 'store_id', has_prior_data)


def product_summary(current_df, prior_df, has_prior_data):
    return _grouped_comparison(current_df, prior_df, 'product', has_prior_data)


def discount_summary(current_df, prior_df, historical_df, has_prior_data, top_n=TOP_DISCOUNTED_COUNT):
    """Top discounted products this period, with margin vs. their typical (historical) margin
    and a profit gain/loss call vs. the prior period."""
    if current_df.empty:
        return []

    current_grouped = current_df.groupby('product').agg(
        sales=('sales', 'sum'), profit=('profit', 'sum'), discount=('discount', 'mean')
    )
    discounted = current_grouped[current_grouped['discount'] > 0].copy()
    if discounted.empty:
        return []

    prior_grouped = prior_df.groupby('product').agg(sales=('sales', 'sum'), profit=('profit', 'sum'))
    historical_grouped = historical_df.groupby('product').agg(sales=('sales', 'sum'), profit=('profit', 'sum'))

    results = []
    for product, row in discounted.iterrows():
        sales = float(row['sales'])
        profit = float(row['profit'])
        margin_now = (profit / sales) if sales != 0 else 0.0

        has_history = product in historical_grouped.index and historical_grouped.loc[product, 'sales'] != 0
        margin_typical = None
        margin_change = None
        if has_history:
            hist_sales = float(historical_grouped.loc[product, 'sales'])
            hist_profit = float(historical_grouped.loc[product, 'profit'])
            margin_typical = hist_profit / hist_sales
            if margin_typical != 0:
                margin_change = (margin_now - margin_typical) / abs(margin_typical)

        had_prior = has_prior_data and product in prior_grouped.index
        prior_profit = float(prior_grouped.loc[product, 'profit']) if had_prior else None
        profit_change_abs = (profit - prior_profit) if had_prior else None

        if profit_change_abs is None:
            impact_label = 'No prior week to compare'
        elif profit_change_abs >= 0:
            impact_label = 'Net profit gain'
        else:
            impact_label = 'Net profit loss'

        results.append({
            'product': product,
            'avg_discount': float(row['discount']),
            'sales': sales,
            'profit': profit,
            'margin_now': margin_now,
            'margin_typical': margin_typical,
            'margin_change': margin_change,
            'profit_change_abs': profit_change_abs,
            'impact_label': impact_label,
        })

    results.sort(key=lambda r: r['avg_discount'], reverse=True)
    return results[:top_n]


def build_flags(category_rows, region_rows, store_rows, product_rows, discount_rows,
                 threshold=DEFAULT_DECLINE_THRESHOLD):
    flags = []

    def add_decline_flags(rows, kind):
        for r in rows:
            if r['sales_change'] is not None and r['sales_change'] <= -threshold:
                flags.append({
                    'kind': kind,
                    'name': r['name'],
                    'change': r['sales_change'],
                })

    add_decline_flags(region_rows, 'region')
    add_decline_flags(category_rows, 'category')
    add_decline_flags(store_rows, 'store')
    add_decline_flags(product_rows, 'product')

    for r in discount_rows:
        if r['margin_change'] is not None and r['margin_change'] <= -MARGIN_DECLINE_THRESHOLD:
            flags.append({
                'kind': 'margin',
                'name': r['product'],
                'change': r['margin_change'],
                'margin_now': r['margin_now'],
                'margin_typical': r['margin_typical'],
            })

    return flags


def _biggest_category_drop_in_region(current_df, prior_df, region):
    """The category with the largest dollar sales decline within a specific region,
    used to make the auto-generated paragraph name a real driver instead of a global guess."""
    region_current = current_df[current_df['region'] == region].groupby('category')['sales'].sum()
    region_prior = prior_df[prior_df['region'] == region].groupby('category')['sales'].sum()
    all_categories = set(region_current.index) | set(region_prior.index)

    worst_category = None
    worst_drop = 0.0
    for category in all_categories:
        cur = float(region_current.get(category, 0.0))
        prior = float(region_prior.get(category, 0.0))
        drop = cur - prior
        if drop < worst_drop:
            worst_drop = drop
            worst_category = category
    return worst_category


def generate_paragraph(flags, current_totals, prior_totals, has_prior_data, current_df=None, prior_df=None,
                        threshold=DEFAULT_DECLINE_THRESHOLD):
    if not has_prior_data:
        return ("No prior week of data was found, so week-over-week comparisons and "
                "flags aren't available yet. Upload a prior week's data to unlock them.")

    region_flags = [f for f in flags if f['kind'] == 'region']
    category_flags = [f for f in flags if f['kind'] == 'category']
    store_flags = [f for f in flags if f['kind'] == 'store']
    product_flags = [f for f in flags if f['kind'] == 'product']
    margin_flags = [f for f in flags if f['kind'] == 'margin']

    if not flags:
        sales_change = _pct_change(current_totals['sales'], prior_totals['sales'])
        direction = 'up' if (sales_change or 0) >= 0 else 'down'
        pct = abs(sales_change * 100) if sales_change is not None else 0.0
        return (f"No significant issues were flagged this week. Total sales were {direction} "
                f"{pct:.1f}% versus last week, with no region, category, store, or product "
                f"showing a decline of more than {threshold * 100:.0f}%.")

    sentences = []

    flagged_category_names = {f['name'] for f in category_flags}
    for f in region_flags:
        driver = ''
        if current_df is not None and prior_df is not None:
            driver_category = _biggest_category_drop_in_region(current_df, prior_df, f['name'])
            if driver_category:
                driver = f", driven mainly by lower {driver_category} sales"
                flagged_category_names.discard(driver_category)
        sentences.append(f"{f['name']} region sales dropped {abs(f['change']) * 100:.0f}% this week{driver}.")

    for f in category_flags:
        if f['name'] not in flagged_category_names:
            continue  # already named as a specific region's driver above
        sentences.append(f"{f['name']} category sales fell {abs(f['change']) * 100:.0f}% versus last week.")

    for f in store_flags[:2]:
        sentences.append(f"Store {f['name']} sales fell {abs(f['change']) * 100:.0f}% versus last week.")

    for f in product_flags[:2]:
        sentences.append(f"{f['name']} sales dropped {abs(f['change']) * 100:.0f}% versus last week.")

    for f in margin_flags[:2]:
        sentences.append(
            f"The discount on {f['name']} appears to be cutting into profit — margin is "
            f"{f['margin_now'] * 100:.0f}% now versus a typical {f['margin_typical'] * 100:.0f}%."
        )

    return ' '.join(sentences)


def build_report(df, current_period=None, prior_period=None, threshold=DEFAULT_DECLINE_THRESHOLD):
    """Run the full weekly summary pipeline on a combined, validated dataset."""
    df = prepare_dataframe(df)

    default_current, default_prior = default_periods(df)
    current_period = current_period or default_current
    prior_period = prior_period or default_prior

    current_df = filter_period(df, current_period)
    prior_df = filter_period(df, prior_period)
    historical_df = df[df['date'] < current_period[0]]

    has_prior_data = not prior_df.empty

    current_totals = {
        'sales': float(current_df['sales'].sum()),
        'profit': float(current_df['profit'].sum()),
        'orders': int(len(current_df)),
    }
    prior_totals = {
        'sales': float(prior_df['sales'].sum()),
        'profit': float(prior_df['profit'].sum()),
        'orders': int(len(prior_df)),
    }

    totals_change = {
        'sales': _pct_change(current_totals['sales'], prior_totals['sales']) if has_prior_data else None,
        'profit': _pct_change(current_totals['profit'], prior_totals['profit']) if has_prior_data else None,
        'orders': _pct_change(current_totals['orders'], prior_totals['orders']) if has_prior_data else None,
    }

    category_rows = category_summary(current_df, prior_df, has_prior_data)
    region_rows = region_summary(current_df, prior_df, has_prior_data)
    store_rows = store_summary(current_df, prior_df, has_prior_data)
    product_rows = product_summary(current_df, prior_df, has_prior_data)
    discount_rows = discount_summary(current_df, prior_df, historical_df, has_prior_data)

    flags = build_flags(category_rows, region_rows, store_rows, product_rows, discount_rows, threshold)
    paragraph = generate_paragraph(flags, current_totals, prior_totals, has_prior_data,
                                    current_df, prior_df, threshold)

    return {
        'current_period': current_period,
        'prior_period': prior_period,
        'has_prior_data': has_prior_data,
        'current_totals': current_totals,
        'prior_totals': prior_totals,
        'totals_change': totals_change,
        'category_rows': category_rows,
        'region_rows': region_rows,
        'store_rows': store_rows,
        'product_rows': product_rows,
        'discount_rows': discount_rows,
        'flags': flags,
        'paragraph': paragraph,
        'threshold': threshold,
    }
