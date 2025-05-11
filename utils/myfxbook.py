from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import pandas as pd
from prettytable import PrettyTable
import time


def get_trading_periods_table(url):
    # Set up headless Chrome
    options = Options()
    options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)

    # Open the URL and wait for dynamic content to load
    driver.get(url)
    time.sleep(5)  # Adjust delay as needed

    # Get the rendered HTML and quit the driver
    html = driver.page_source
    driver.quit()

    # Parse the page content using BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    # Find the trading periods table by its ID
    table = soup.find("table", id="tradingPeriodsTable")
    if table is None:
        raise Exception("Trading periods table not found.")

    # Extract table headers
    headers = []
    thead = table.find("thead")
    if thead:
        header_row = thead.find("tr")
        for th in header_row.find_all("th"):
            headers.append(th.get_text(strip=True))
    else:
        raise Exception("Table header not found.")

    # Extract table rows from tbody
    data_rows = []
    tbody = table.find("tbody")
    if tbody:
        for tr in tbody.find_all("tr"):
            # Using split() will help to manage nested spans
            row = [td.get_text(separator=" ", strip=True) for td in tr.find_all("td")]
            if row:
                data_rows.append(row)
    else:
        raise Exception("Table body not found.")

    # Create a DataFrame from the extracted data
    df = pd.DataFrame(data_rows, columns=headers)
    return df


def get_gain_by_flag(flag, df):
    """
    Given a flag ('Today', 'Week', 'Month', or 'Year'), this function returns
    the gain percentage (only the first number) for the corresponding period.
    """
    flag = flag.lower()
    mapping = {
        'today': 'Today',
        'week': 'This Week',
        'month': 'This Month',
        'year': 'This Year'
    }
    if flag not in mapping:
        raise ValueError("Invalid flag. Use one of: 'Today', 'Week', 'Month', or 'Year'.")
    period_keyword = mapping[flag]

    # Assume the first column in the DataFrame holds the period names.
    matching_row = df[df.iloc[:, 0].str.contains(period_keyword, case=False)]
    if matching_row.empty:
        return None

    # Get the "Gain (Difference)" cell
    gain_str = matching_row.iloc[0]["Gain (Difference)"]
    # Extract only the first part (e.g., "+2.72%")
    gain_value = gain_str.split()[0]
    return gain_value


def main():
    url = "https://www.myfxbook.com/members/fiatelpis2/fiatelpis-central-iv-fusion/10569665"
    try:
        df = get_trading_periods_table(url)
    except Exception as e:
        print("Error retrieving table:", e)
        return

    # Display the full table using pandas
    print("Trading Periods Table (Pandas DataFrame):")
    print(df)
    print("\n")

    # Display the table using PrettyTable
    pt = PrettyTable(df.columns.tolist())
    for _, row in df.iterrows():
        pt.add_row(row.tolist())
    print("Trading Periods Table (PrettyTable):")
    print(pt)
    print("\n")

    # Get and display gain values based on flags
    for flag in ["today", "week", "month", "year"]:
        gain = get_gain_by_flag(flag, df)
        print(f"Gain for {flag.capitalize()}: {gain}")


if __name__ == '__main__':
    main()
