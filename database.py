import sqlite3
import json

def initDB():
  dbfile = "llm_twins.db"
  conn = sqlite3.connect(dbfile)
  cursor = conn.cursor()
  cursor.execute("CREATE TABLE IF NOT EXISTS llm_twins (name TEXT, description TEXT)")
  cursor.execute("CREATE TABLE IF NOT EXISTS llm_twins_api (name TEXT, api_table TEXT)")
  conn.commit()
  cursor.close()

  return conn, cursor

def selectFromDB(conn, table_name, column_name, value):
    try:
      cursor = conn.cursor()
      # 使用變量來構造 SQL 查詢，注意 SQL 注入的風險，這裡使用參數化查詢來避免
      query = f"SELECT * FROM {table_name} WHERE {column_name}=?"
      cursor.execute(query, (value,))
      result = cursor.fetchone()
      cursor.close()
      return result
    except Exception as e:
       return False

# Insert or update  profile to database
def insertOrUpdateProfile(conn, table_name, column_name, value, profile):
    try:
      cursor = conn.cursor()
      # 使用變量來構造 SQL 查詢，注意 SQL 注入的風險，這裡使用參數化查詢來避免
      query = f"SELECT * FROM {table_name} WHERE {column_name}=?"
      cursor.execute(query, (value,))
      result = cursor.fetchone()

      if result:
        # Update the profile
        cursor.execute(f"UPDATE {table_name} SET description=? WHERE name=?", (profile["描述"], value))
        conn.commit()
      else:
        # Insert the profile
        cursor.execute(f"INSERT INTO {table_name} (name, description) VALUES (?, ?)", (value, profile["描述"]))
        conn.commit()

      cursor.close()

      return True
    except Exception as e:
       return False

def saveProfileToDB(conn, user):
    try:
      cursor = conn.cursor()
      cursor.execute("INSERT INTO llm_twins (name, description) VALUES (?, ?)", (user.name, user.description))
      conn.commit()
      cursor.close()
    except Exception as e:
      return False

    return True

# Insert or update API table to database
def insertOrUpdateAPITable(conn, table_name, column_name, value, api_table):
    try:
      cursor = conn.cursor()
      # 使用變量來構造 SQL 查詢，注意 SQL 注入的風險，這裡使用參數化查詢來避免
      query = f"SELECT * FROM {table_name} WHERE {column_name}=?"
      cursor.execute(query, (value,))
      result = cursor.fetchone()

      if result:
        # Update the profile
        cursor.execute(f"UPDATE {table_name} SET api_table=? WHERE name=?", (json.dumps(api_table), value))
        conn.commit()
      else:
        # Insert the profile
        cursor.execute(f"INSERT INTO {table_name} (name, api_table) VALUES (?, ?)", (value, json.dumps(api_table)))
        conn.commit()

      cursor.close()

      return True
    except Exception as e:
       return False

def saveAPITableToDB(conn, user, api_table):
    try:
      cursor = conn.cursor()
      cursor.execute("INSERT INTO llm_twins_api (name, api_table) VALUES (?, ?)", (user.name, json.dumps(api_table)))
      conn.commit()
      cursor.close()
    except Exception as e:
      return False

    return True

def deleteFromDB(conn, table_name, column_name, value):
    try:
      cursor = conn.cursor()
      cursor.execute(f"DELETE FROM {table_name} WHERE {column_name}=?", (value,))
      conn.commit()
      cursor.close()
    except Exception as e:
      return False

    return True

def listFromDB(conn, table_name):
    try:
      cursor = conn.cursor()
      cursor.execute(f"SELECT * FROM {table_name}")
      result = cursor.fetchall()
      cursor.close()
    except Exception as e:
      return None

    return result