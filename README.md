# Weekly Sales Summary

A tool that turns your weekly sales export files into an organized report —
automatically. No spreadsheets, no manual math. Load your files, click
Generate Report, and you get a ready-to-share summary in about a minute.

## What it does

1. **You load one or more files** — CSV, Excel, or tab-separated exports.
   You can load several at once (for example, one file per region, or one
   file per week).
2. **It checks your files for problems** — missing columns, blank values,
   text where a number should be, dates it can't understand — and tells you
   exactly what's wrong and in which file, in plain English. If something's
   off, it won't let you generate a report until it's fixed.
3. **It builds this week's report**, comparing everything to last week:
   - A short written summary at the top, in plain language
   - Total sales, profit, and orders, with the % change vs. last week
   - A callout box listing anything that's down more than 10% (region,
     category, store, or product) so you don't have to go hunting for it
   - Sales by region and by category, each with % change
   - Sales by store, so you can spot a specific location that's struggling
   - A table of your most-discounted products, showing whether the
     discount is helping or hurting profit margin
4. **You export it** to an Excel file you can forward to your regional
   managers.

## What your files need to have

Each file needs these columns (the exact column order doesn't matter, and
extra spacing/capitalization in the header names is fine):

| Column   | What goes here                                  |
|----------|--------------------------------------------------|
| date     | The order date                                   |
| region   | e.g. East, West, Central, South                  |
| category | e.g. Furniture, Supplies, Technology              |
| product  | Product name                                      |
| sales    | Sale amount in dollars                            |
| discount | Discount applied (e.g. 0.10 for 10%, or 10)       |
| profit   | Profit in dollars                                 |
| store_id | Store or location identifier                     |

## How to run it

You'll need Python installed on your computer (ask IT if you're not sure —
this only needs to be set up once).

**First-time setup** (open Terminal, then paste these lines one at a time):

```
cd path/to/sales-coordinator-project
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Every time you want to use the app:**

```
cd path/to/sales-coordinator-project
source venv/bin/activate
python3 main.py
```

A window will open. From there:

1. Click **Load Data Files...** and select your file(s).
2. Check the list — anything marked "Problem" needs to be fixed or removed
   before you can continue (click it to see the details, or click
   **Remove Selected** to take it out of the batch).
3. Once everything says "OK," click **Generate Report**.
4. Review the report window — the summary paragraph, flagged issues, and
   breakdown tables.
5. Click **Export / Share Report...** to save it as an Excel file you can
   email to your managers.

## Try it with sample data first

The `sample_data/` folder has example files you can load right away to see
how it works:

- `week_2026-07-13_all_regions.csv` — a full prior week, all regions
- `week_2026-07-20_east_central.csv` and `week_2026-07-20_west_south.csv` —
  the current week, split across two files (to show that loading multiple
  files for the same week works)
- `invalid_export_example.csv` — a file with a few intentional problems
  (a blank region, a non-numeric profit value, a bad date), so you can see
  what the "Problem" flow looks like

Load the three valid files together and generate a report — you should see
a flagged decline in the West region driven by furniture sales, and a
flagged margin drop on a discounted Office Chair sale in the West. Then try
loading the invalid file on its own to see the plain-English error messages.

## Good to know (current limitations)

- This is a single-user tool that runs on your computer — there's no login,
  no shared database, and nothing is uploaded anywhere.
- It compares "this week" (the most recent week in your data) to the week
  right before it. It doesn't yet keep a history across many weeks.
- It only reads files you load — it doesn't connect to any sales system
  directly.
- Reports export to Excel only for now.
