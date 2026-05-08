import os
import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv

def export_mongo_to_csv():
    # Load environment variables
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    load_dotenv(dotenv_path=env_path)
    
    uri = os.getenv("MONGODB_URI", "").strip()
    if not uri:
        print("Error: MONGODB_URI not found in .env file.")
        return
        
    print("Connecting to MongoDB Atlas...")
    try:
        # Connect to MongoDB
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        db = client["gold_agent"]
        collection = db["trade_log"]
        
        # Fetch all documents (excluding the MongoDB object ID)
        print("Fetching data from 'trade_log' collection...")
        cursor = collection.find({}, {"_id": 0})
        data = list(cursor)
        
        if not data:
            print("No data found in the trade_log collection.")
            return
            
        # Convert to pandas DataFrame
        df = pd.DataFrame(data)
        
        # Determine save path
        save_path = os.path.join(os.path.dirname(__file__), "..", "data", "mongo_export_trade_log.csv")
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        
        # Save to CSV
        df.to_csv(save_path, index=False, encoding="utf-8")
        print(f"Success! Exported {len(df)} rows to: {save_path}")
        
    except Exception as e:
        print(f"An error occurred during export: {e}")

if __name__ == "__main__":
    export_mongo_to_csv()
