$latestLog = Get-ChildItem 'C:\Program Files\PostgreSQL\18\data\log' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Get-Content $latestLog.FullName -Tail 50