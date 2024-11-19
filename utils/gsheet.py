import pygsheets

def write_to_cell(worksheet, cell, value):
    # 寫入值到儲存格
    worksheet.update_value(cell, value)

def extract_profile_from_sheet(worksheet):
    # 讀取 A 和 B 列的所有數據
    data = worksheet.get_all_values(include_tailing_empty_rows=False)

    # 創建字典來存儲配置文件信息
    dict_profile = {}

    # 迭代數據並填充字典
    for row in data:
        if len(row) >= 2 and row[0] and row[1]:  # 確保行有兩個非空元素
            dict_profile[row[0]] = row[1]
        else:
            break  # 遇到空行則結束循環

    return dict_profile