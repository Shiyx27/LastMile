import pandas as pd
from flask import Flask, request, render_template

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        file = request.files['file']
        if not file:
            print("No file received")  # Debugging
            return "No file received", 400

        try:
            df = pd.read_csv(file)
            print("File loaded successfully")  # Debugging
        except Exception as e:
            print("Error reading file:", e)  # Debugging
            return f"Error reading file: {e}", 400

        print("Columns in file:", df.columns)  # Debugging
        required_columns = ['Order Creation Date', 'Vehicle Number', 'Manual End Odometer (in meters)',
                            'Manual Start Odometer (in meters)', 'GPS Available',
                            'Trip GPS Distance Travelled (in KM)', 'Manual Distance Travelled (in KM)', 'Zone', 'Hub']

        for col in required_columns:
            if col not in df.columns:
                print(f"Missing column: {col}")  # Debugging
                return f"Missing required column: {col}", 400

        df['Order Creation Date'] = pd.to_datetime(df['Order Creation Date'], errors='coerce')
        df = df.sort_values(by=['Vehicle Number', 'Order Creation Date'], ascending=[True, True])

        df['Prev Manual End Odometer'] = df.groupby('Vehicle Number', group_keys=False)['Manual End Odometer (in meters)'].shift(1, fill_value=pd.NA)

        def detect_risk(row):
            if 'Parent Vehicle Number' in df.columns and pd.notna(row.get('Parent Vehicle Number')):
                return row['Order Creation Date'], row['Vehicle Number'], None, None, 0
            risks = set()
            reasons = set()
            risk_value = 0

            if pd.notna(row['Prev Manual End Odometer']) and pd.notna(row['Manual Start Odometer (in meters)']):
                if row['Manual Start Odometer (in meters)'] < row['Prev Manual End Odometer']:
                    risks.add("Odometer inconsistency")
                    reasons.add("Odometer reading is less than the previous day's end reading")
                    risk_value += 20

            if row['GPS Available'] == 'Yes':
                if pd.notna(row['Trip GPS Distance Travelled (in KM)']) and pd.notna(row['Manual Distance Travelled (in KM)']):
                    if abs(row['Manual Distance Travelled (in KM)'] - row['Trip GPS Distance Travelled (in KM)']) > 0.1:
                        risks.add("GPS discrepancy")
                        reasons.add("GPS distance and manual distance differ significantly")
                        risk_value += 10

            if pd.notna(row['Manual Distance Travelled (in KM)']) and row['Manual Distance Travelled (in KM)'] > 125:
                risks.add("Excessive travel distance")
                reasons.add("Manual distance travelled exceeds 125 KM in a day")
                risk_value += 15

            return row['Order Creation Date'], row['Vehicle Number'], '; '.join(risks) if risks else None, '; '.join(reasons) if reasons else None, risk_value

        df[['Date', 'Vehicle Number', 'Risk Factors', 'Reasoning', 'Risk Value']] = df.apply(detect_risk, axis=1, result_type='expand')

        print("Processed DataFrame Head:\n", df.head())  # Debugging

        deviations_df = df[df['Risk Factors'].notna()][['Zone', 'Hub', 'Vehicle Number', 'Date', 'Risk Factors', 'Reasoning', 'Risk Value']]

        grouped_deviations = deviations_df.groupby(['Zone', 'Hub', 'Vehicle Number']).agg({
            'Date': lambda x: ', '.join(sorted(set(x.astype(str)))),
            'Risk Factors': lambda x: '; '.join(sorted(set(x.dropna()))),
            'Reasoning': lambda x: '; '.join(sorted(set(x.dropna()))) if x.dropna().any() else "No Reason Provided",
            'Risk Value': 'sum'
        }).reset_index()

        print("Grouped Deviations Head:\n", grouped_deviations.head())  # Debugging

        top_20_hubs = grouped_deviations.groupby(['Zone', 'Hub']).agg({
            'Vehicle Number': lambda x: ', '.join(sorted(set(x))),
            'Risk Value': 'sum'
        }).reset_index().sort_values(by='Risk Value', ascending=False).head(20)

        top_20_per_zone = grouped_deviations.sort_values(by=['Zone', 'Risk Value'], ascending=[True, False])
        top_20_per_zone = top_20_per_zone.groupby('Zone').head(20)

        print("Top 20 Hubs:\n", top_20_hubs.head())  # Debugging
        print("Top 20 Per Zone:\n", top_20_per_zone.head())  # Debugging

        return render_template('index.html', top_20_hubs=top_20_hubs.to_dict(orient='records'),
                               top_20_per_zone=top_20_per_zone.to_dict(orient='records'), grouped_data=grouped_deviations.to_dict(orient='records'),
                               file_ready=True)

    return render_template('index.html', top_20_hubs=[], top_20_per_zone=[], grouped_data=[], file_ready=False)

if __name__ == '__main__':
    
    
    port = int(os.environ.get("PORT", 5000))  # Use Render's assigned port
    app.run(host='0.0.0.0', port=port)
