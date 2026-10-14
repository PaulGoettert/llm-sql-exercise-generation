# Diff3: echte PORT_COL_NAME-Beispiele aus dem Baseline-Durchlauf

Quelle: `prep_step2_arctic_new_prompt/analyse feedback2/step2_output_diff3_afterlint2.json`

Hinweis: `PORT_COL_NAME` ist hier eine SQLLint-Portabilitaetswarnung. Sie tritt bei diff3 haeufig auf, weil `NOT EXISTS`-Subqueries oft `SELECT 1` verwenden; `1` ist keine Spaltenreferenz und hat keinen expliziten Output-Alias.

## Beispiel 1

- `entry_index`: `0`
- `db_id`: `department_management`
- gematchter Prompt: `1`
- Lint-Detail: `[{"code": "PORT_COL_NAME", "description": "Implicit col might not be portable"}]`

### SQL Query

```sql
SELECT d.`Department_ID`, d.`Name`, d.`Creation`, d.`Ranking`, d.`Budget_in_Billions`, d.`Num_Employees` FROM `department` AS d WHERE NOT EXISTS(SELECT 1 FROM `management` AS m WHERE m.`Department_ID` = d.`Department_ID` AND m.`temporary_acting` = 'Yes')
```

### Schema

- **department**(Department_ID INT, Name TEXT, Creation TEXT, Ranking INT, Budget_in_Billions REAL, Num_Employees REAL)
- **head**(head_ID INT, name TEXT, born_state TEXT, age REAL)
- **management**(department_ID INT, head_ID INT, temporary_acting TEXT)


### Primary Keys

- department: Department_ID
- head: head_ID
- management: department_ID, head_ID


### Foreign Keys

- management.Department_ID = department.Department_ID
- management.head_ID = head.head_ID


### Sample Rows (Auszug)

**department**
- `{"Department_ID": 5, "Name": "Interior", "Creation": "1849", "Ranking": 5, "Budget_in_Billions": 10.7, "Num_Employees": 71436.0}`
- `{"Department_ID": 8, "Name": "Labor", "Creation": "1913", "Ranking": 8, "Budget_in_Billions": 59.7, "Num_Employees": 17347.0}`
**head**
- `{"head_ID": 2, "name": "Sergio García", "born_state": "California", "age": 68.0}`
- `{"head_ID": 9, "name": "Pádraig Harrington", "born_state": "Connecticut", "age": 43.0}`
**management**
- `{"department_ID": 11, "head_ID": 10, "temporary_acting": "No"}`
- `{"department_ID": 7, "head_ID": 3, "temporary_acting": "No"}`


### Warum PORT_COL_NAME hier wahrscheinlich ausgeloest wird

Die Query verwendet in einer `NOT EXISTS`-Subquery `SELECT 1`. Das ist SQL-semantisch ueblich, aber SQLLint betrachtet die Konstante `1` als SELECT-Ausdruck ohne expliziten Output-Spaltennamen. Dadurch entsteht die Portabilitaetswarnung `PORT_COL_NAME`.

## Beispiel 2

- `entry_index`: `2`
- `db_id`: `department_management`
- gematchter Prompt: `1`
- Lint-Detail: `[{"code": "PORT_COL_NAME", "description": "Implicit col might not be portable"}]`

### SQL Query

```sql
SELECT * FROM `department` AS d WHERE NOT EXISTS(SELECT 1 FROM `management` AS m WHERE m.`Department_ID` = d.`Department_ID`)
```

### Schema

- **department**(Department_ID INT, Name TEXT, Creation TEXT, Ranking INT, Budget_in_Billions REAL, Num_Employees REAL)
- **head**(head_ID INT, name TEXT, born_state TEXT, age REAL)
- **management**(department_ID INT, head_ID INT, temporary_acting TEXT)


### Primary Keys

- department: Department_ID
- head: head_ID
- management: department_ID, head_ID


### Foreign Keys

- management.Department_ID = department.Department_ID
- management.head_ID = head.head_ID


### Sample Rows (Auszug)

**department**
- `{"Department_ID": 5, "Name": "Interior", "Creation": "1849", "Ranking": 5, "Budget_in_Billions": 10.7, "Num_Employees": 71436.0}`
- `{"Department_ID": 8, "Name": "Labor", "Creation": "1913", "Ranking": 8, "Budget_in_Billions": 59.7, "Num_Employees": 17347.0}`
**head**
- `{"head_ID": 2, "name": "Sergio García", "born_state": "California", "age": 68.0}`
- `{"head_ID": 9, "name": "Pádraig Harrington", "born_state": "Connecticut", "age": 43.0}`
**management**
- `{"department_ID": 11, "head_ID": 10, "temporary_acting": "No"}`
- `{"department_ID": 7, "head_ID": 3, "temporary_acting": "No"}`


### Warum PORT_COL_NAME hier wahrscheinlich ausgeloest wird

Die Query verwendet in einer `NOT EXISTS`-Subquery `SELECT 1`. Das ist SQL-semantisch ueblich, aber SQLLint betrachtet die Konstante `1` als SELECT-Ausdruck ohne expliziten Output-Spaltennamen. Dadurch entsteht die Portabilitaetswarnung `PORT_COL_NAME`.

## Beispiel 3

- `entry_index`: `3`
- `db_id`: `department_management`
- gematchter Prompt: `1`
- Lint-Detail: `[{"code": "PORT_COL_NAME", "description": "Implicit col might not be portable"}]`

### SQL Query

```sql
SELECT 'Department' AS `Type`, d.`Name` AS `Name` FROM `department` AS d WHERE NOT EXISTS(SELECT 1 FROM `management` AS m WHERE m.`Department_ID` = d.`Department_ID`)
```

### Schema

- **department**(Department_ID INT, Name TEXT, Creation TEXT, Ranking INT, Budget_in_Billions REAL, Num_Employees REAL)
- **head**(head_ID INT, name TEXT, born_state TEXT, age REAL)
- **management**(department_ID INT, head_ID INT, temporary_acting TEXT)


### Primary Keys

- department: Department_ID
- head: head_ID
- management: department_ID, head_ID


### Foreign Keys

- management.Department_ID = department.Department_ID
- management.head_ID = head.head_ID


### Sample Rows (Auszug)

**department**
- `{"Department_ID": 5, "Name": "Interior", "Creation": "1849", "Ranking": 5, "Budget_in_Billions": 10.7, "Num_Employees": 71436.0}`
- `{"Department_ID": 8, "Name": "Labor", "Creation": "1913", "Ranking": 8, "Budget_in_Billions": 59.7, "Num_Employees": 17347.0}`
**head**
- `{"head_ID": 2, "name": "Sergio García", "born_state": "California", "age": 68.0}`
- `{"head_ID": 9, "name": "Pádraig Harrington", "born_state": "Connecticut", "age": 43.0}`
**management**
- `{"department_ID": 11, "head_ID": 10, "temporary_acting": "No"}`
- `{"department_ID": 7, "head_ID": 3, "temporary_acting": "No"}`


### Warum PORT_COL_NAME hier wahrscheinlich ausgeloest wird

Die Query verwendet in einer `NOT EXISTS`-Subquery `SELECT 1`. Das ist SQL-semantisch ueblich, aber SQLLint betrachtet die Konstante `1` als SELECT-Ausdruck ohne expliziten Output-Spaltennamen. Dadurch entsteht die Portabilitaetswarnung `PORT_COL_NAME`.

## Beispiel 4

- `entry_index`: `5`
- `db_id`: `farm`
- gematchter Prompt: `3`
- Lint-Detail: `[{"code": "BGE_27", "description": "Missing join condition"}, {"code": "PORT_COL_NAME", "description": "Implicit col might not be portable"}]`

### SQL Query

```sql
SELECT c.`Official_Name` AS `City_Name`, f.`Year`, f.`Total_Horses`, f.`Working_Horses`, f.`Total_Cattle`, f.`Oxen`, f.`Bulls`, f.`Cows`, f.`Pigs`, f.`Sheep_and_Goats` FROM `city` AS c JOIN `farm_competition` AS fc ON c.`City_ID` = fc.`Host_city_ID` JOIN `farm` AS f ON fc.`Competition_ID` = f.`Farm_ID` WHERE NOT EXISTS(SELECT 1 FROM `competition_record` AS cr WHERE cr.`Farm_ID` = f.`Farm_ID` AND cr.`Competition_ID` = fc.`Competition_ID` AND cr.`Rank` <= 3)
```

### Schema

- **city**(City_ID INT, Official_Name TEXT, Status TEXT, Area_km_2 REAL, Population REAL, Census_Ranking TEXT)
- **farm**(Farm_ID INT, Year INT, Total_Horses REAL, Working_Horses REAL, Total_Cattle REAL, Oxen REAL, Bulls REAL, Cows REAL, Pigs REAL, Sheep_and_Goats REAL)
- **farm_competition**(Competition_ID INT, Year INT, Theme TEXT, Host_city_ID INT, Hosts TEXT)
- **competition_record**(Competition_ID INT, Farm_ID INT, Rank INT)


### Primary Keys

- city: City_ID
- farm: Farm_ID
- farm_competition: Competition_ID
- competition_record: Competition_ID, Farm_ID


### Foreign Keys

- farm_competition.Host_city_ID = city.City_ID
- competition_record.Competition_ID = farm_competition.Competition_ID
- competition_record.Farm_ID = farm.Farm_ID


### Sample Rows (Auszug)

**city**
- `{"City_ID": 4, "Official_Name": "Drummond", "Status": "Village", "Area_km_2": 8.91, "Population": 775.0, "Census_Ranking": "2418 of 5008"}`
- `{"City_ID": 2, "Official_Name": "Perth-Andover", "Status": "Village", "Area_km_2": 8.89, "Population": 1778.0, "Census_Ranking": "1442 of 5,008"}`
**farm**
- `{"Farm_ID": 6, "Year": 1932, "Total_Horses": 3658.9, "Working_Horses": 3711.6, "Total_Cattle": 5006.7, "Oxen": 105.2, "Bulls": 71.6, "Cows": 2739.5, "Pigs": 2623.7, "Sheep_and_Goats": 2109.5}`
- `{"Farm_ID": 2, "Year": 1928, "Total_Horses": 5486.9, "Working_Horses": 4090.5, "Total_Cattle": 8604.8, "Oxen": 895.3, "Bulls": 32.8, "Cows": 3987.0, "Pigs": 6962.9, "Sheep_and_Goats": 8112.2}`
**farm_competition**
- `{"Competition_ID": 3, "Year": 2005, "Theme": "MTV Asia Aid", "Host_city_ID": 3, "Hosts": "Alicia Keys"}`
- `{"Competition_ID": 2, "Year": 2006, "Theme": "Codehunters", "Host_city_ID": 2, "Hosts": "Leehom Wang and Kelly Rowland"}`


### Warum PORT_COL_NAME hier wahrscheinlich ausgeloest wird

Die Query verwendet in einer `NOT EXISTS`-Subquery `SELECT 1`. Das ist SQL-semantisch ueblich, aber SQLLint betrachtet die Konstante `1` als SELECT-Ausdruck ohne expliziten Output-Spaltennamen. Dadurch entsteht die Portabilitaetswarnung `PORT_COL_NAME`.

## Beispiel 5

- `entry_index`: `6`
- `db_id`: `farm`
- gematchter Prompt: `1`
- Lint-Detail: `[{"code": "PORT_COL_NAME", "description": "Implicit col might not be portable"}]`

### SQL Query

```sql
SELECT c.`Official_Name` FROM `city` AS c WHERE NOT EXISTS(SELECT 1 FROM `farm_competition` AS fc WHERE fc.`Host_city_ID` = c.`City_ID`)
```

### Schema

- **city**(City_ID INT, Official_Name TEXT, Status TEXT, Area_km_2 REAL, Population REAL, Census_Ranking TEXT)
- **farm**(Farm_ID INT, Year INT, Total_Horses REAL, Working_Horses REAL, Total_Cattle REAL, Oxen REAL, Bulls REAL, Cows REAL, Pigs REAL, Sheep_and_Goats REAL)
- **farm_competition**(Competition_ID INT, Year INT, Theme TEXT, Host_city_ID INT, Hosts TEXT)
- **competition_record**(Competition_ID INT, Farm_ID INT, Rank INT)


### Primary Keys

- city: City_ID
- farm: Farm_ID
- farm_competition: Competition_ID
- competition_record: Competition_ID, Farm_ID


### Foreign Keys

- farm_competition.Host_city_ID = city.City_ID
- competition_record.Competition_ID = farm_competition.Competition_ID
- competition_record.Farm_ID = farm.Farm_ID


### Sample Rows (Auszug)

**city**
- `{"City_ID": 4, "Official_Name": "Drummond", "Status": "Village", "Area_km_2": 8.91, "Population": 775.0, "Census_Ranking": "2418 of 5008"}`
- `{"City_ID": 2, "Official_Name": "Perth-Andover", "Status": "Village", "Area_km_2": 8.89, "Population": 1778.0, "Census_Ranking": "1442 of 5,008"}`
**farm**
- `{"Farm_ID": 6, "Year": 1932, "Total_Horses": 3658.9, "Working_Horses": 3711.6, "Total_Cattle": 5006.7, "Oxen": 105.2, "Bulls": 71.6, "Cows": 2739.5, "Pigs": 2623.7, "Sheep_and_Goats": 2109.5}`
- `{"Farm_ID": 2, "Year": 1928, "Total_Horses": 5486.9, "Working_Horses": 4090.5, "Total_Cattle": 8604.8, "Oxen": 895.3, "Bulls": 32.8, "Cows": 3987.0, "Pigs": 6962.9, "Sheep_and_Goats": 8112.2}`
**farm_competition**
- `{"Competition_ID": 3, "Year": 2005, "Theme": "MTV Asia Aid", "Host_city_ID": 3, "Hosts": "Alicia Keys"}`
- `{"Competition_ID": 2, "Year": 2006, "Theme": "Codehunters", "Host_city_ID": 2, "Hosts": "Leehom Wang and Kelly Rowland"}`


### Warum PORT_COL_NAME hier wahrscheinlich ausgeloest wird

Die Query verwendet in einer `NOT EXISTS`-Subquery `SELECT 1`. Das ist SQL-semantisch ueblich, aber SQLLint betrachtet die Konstante `1` als SELECT-Ausdruck ohne expliziten Output-Spaltennamen. Dadurch entsteht die Portabilitaetswarnung `PORT_COL_NAME`.

## Beispiel 6

- `entry_index`: `7`
- `db_id`: `farm`
- gematchter Prompt: `3`
- Lint-Detail: `[{"code": "BGE_27", "description": "Missing join condition"}, {"code": "PORT_COL_NAME", "description": "Implicit col might not be portable"}]`

### SQL Query

```sql
SELECT c.`Official_Name` AS `City_Name`, f.`Year` AS `Farm_Year`, f.`Total_Horses`, f.`Working_Horses`, f.`Total_Cattle`, f.`Oxen`, f.`Bulls`, f.`Cows`, f.`Pigs`, f.`Sheep_and_Goats` FROM `city` AS c JOIN `farm_competition` AS fc ON c.`City_ID` = fc.`Host_city_ID` JOIN `farm` AS f ON fc.`Competition_ID` = f.`Farm_ID` WHERE NOT EXISTS(SELECT 1 FROM `competition_record` AS cr WHERE cr.`Competition_ID` = fc.`Competition_ID` AND cr.`Farm_ID` = f.`Farm_ID` AND cr.`Rank` > 3)
```

### Schema

- **city**(City_ID INT, Official_Name TEXT, Status TEXT, Area_km_2 REAL, Population REAL, Census_Ranking TEXT)
- **farm**(Farm_ID INT, Year INT, Total_Horses REAL, Working_Horses REAL, Total_Cattle REAL, Oxen REAL, Bulls REAL, Cows REAL, Pigs REAL, Sheep_and_Goats REAL)
- **farm_competition**(Competition_ID INT, Year INT, Theme TEXT, Host_city_ID INT, Hosts TEXT)
- **competition_record**(Competition_ID INT, Farm_ID INT, Rank INT)


### Primary Keys

- city: City_ID
- farm: Farm_ID
- farm_competition: Competition_ID
- competition_record: Competition_ID, Farm_ID


### Foreign Keys

- farm_competition.Host_city_ID = city.City_ID
- competition_record.Competition_ID = farm_competition.Competition_ID
- competition_record.Farm_ID = farm.Farm_ID


### Sample Rows (Auszug)

**city**
- `{"City_ID": 4, "Official_Name": "Drummond", "Status": "Village", "Area_km_2": 8.91, "Population": 775.0, "Census_Ranking": "2418 of 5008"}`
- `{"City_ID": 2, "Official_Name": "Perth-Andover", "Status": "Village", "Area_km_2": 8.89, "Population": 1778.0, "Census_Ranking": "1442 of 5,008"}`
**farm**
- `{"Farm_ID": 6, "Year": 1932, "Total_Horses": 3658.9, "Working_Horses": 3711.6, "Total_Cattle": 5006.7, "Oxen": 105.2, "Bulls": 71.6, "Cows": 2739.5, "Pigs": 2623.7, "Sheep_and_Goats": 2109.5}`
- `{"Farm_ID": 2, "Year": 1928, "Total_Horses": 5486.9, "Working_Horses": 4090.5, "Total_Cattle": 8604.8, "Oxen": 895.3, "Bulls": 32.8, "Cows": 3987.0, "Pigs": 6962.9, "Sheep_and_Goats": 8112.2}`
**farm_competition**
- `{"Competition_ID": 3, "Year": 2005, "Theme": "MTV Asia Aid", "Host_city_ID": 3, "Hosts": "Alicia Keys"}`
- `{"Competition_ID": 2, "Year": 2006, "Theme": "Codehunters", "Host_city_ID": 2, "Hosts": "Leehom Wang and Kelly Rowland"}`


### Warum PORT_COL_NAME hier wahrscheinlich ausgeloest wird

Die Query verwendet in einer `NOT EXISTS`-Subquery `SELECT 1`. Das ist SQL-semantisch ueblich, aber SQLLint betrachtet die Konstante `1` als SELECT-Ausdruck ohne expliziten Output-Spaltennamen. Dadurch entsteht die Portabilitaetswarnung `PORT_COL_NAME`.

## Beispiel 7

- `entry_index`: `9`
- `db_id`: `farm`
- gematchter Prompt: `2`
- Lint-Detail: `[{"code": "BGE_27", "description": "Missing join condition"}, {"code": "PORT_COL_NAME", "description": "Implicit col might not be portable"}]`

### SQL Query

```sql
SELECT c.`Official_Name` AS `City_Name`, f.`Year`, f.`Total_Horses`, f.`Working_Horses`, f.`Total_Cattle`, f.`Oxen`, f.`Bulls`, f.`Cows`, f.`Pigs`, f.`Sheep_and_Goats` FROM `city` AS c JOIN `farm_competition` AS fc ON c.`City_ID` = fc.`Host_city_ID` JOIN `farm` AS f ON fc.`Competition_ID` = f.`Farm_ID` WHERE NOT EXISTS(SELECT 1 FROM `competition_record` AS cr WHERE cr.`Competition_ID` = fc.`Competition_ID` AND cr.`Rank` <= 3)
```

### Schema

- **city**(City_ID INT, Official_Name TEXT, Status TEXT, Area_km_2 REAL, Population REAL, Census_Ranking TEXT)
- **farm**(Farm_ID INT, Year INT, Total_Horses REAL, Working_Horses REAL, Total_Cattle REAL, Oxen REAL, Bulls REAL, Cows REAL, Pigs REAL, Sheep_and_Goats REAL)
- **farm_competition**(Competition_ID INT, Year INT, Theme TEXT, Host_city_ID INT, Hosts TEXT)
- **competition_record**(Competition_ID INT, Farm_ID INT, Rank INT)


### Primary Keys

- city: City_ID
- farm: Farm_ID
- farm_competition: Competition_ID
- competition_record: Competition_ID, Farm_ID


### Foreign Keys

- farm_competition.Host_city_ID = city.City_ID
- competition_record.Competition_ID = farm_competition.Competition_ID
- competition_record.Farm_ID = farm.Farm_ID


### Sample Rows (Auszug)

**city**
- `{"City_ID": 4, "Official_Name": "Drummond", "Status": "Village", "Area_km_2": 8.91, "Population": 775.0, "Census_Ranking": "2418 of 5008"}`
- `{"City_ID": 2, "Official_Name": "Perth-Andover", "Status": "Village", "Area_km_2": 8.89, "Population": 1778.0, "Census_Ranking": "1442 of 5,008"}`
**farm**
- `{"Farm_ID": 6, "Year": 1932, "Total_Horses": 3658.9, "Working_Horses": 3711.6, "Total_Cattle": 5006.7, "Oxen": 105.2, "Bulls": 71.6, "Cows": 2739.5, "Pigs": 2623.7, "Sheep_and_Goats": 2109.5}`
- `{"Farm_ID": 2, "Year": 1928, "Total_Horses": 5486.9, "Working_Horses": 4090.5, "Total_Cattle": 8604.8, "Oxen": 895.3, "Bulls": 32.8, "Cows": 3987.0, "Pigs": 6962.9, "Sheep_and_Goats": 8112.2}`
**farm_competition**
- `{"Competition_ID": 3, "Year": 2005, "Theme": "MTV Asia Aid", "Host_city_ID": 3, "Hosts": "Alicia Keys"}`
- `{"Competition_ID": 2, "Year": 2006, "Theme": "Codehunters", "Host_city_ID": 2, "Hosts": "Leehom Wang and Kelly Rowland"}`


### Warum PORT_COL_NAME hier wahrscheinlich ausgeloest wird

Die Query verwendet in einer `NOT EXISTS`-Subquery `SELECT 1`. Das ist SQL-semantisch ueblich, aber SQLLint betrachtet die Konstante `1` als SELECT-Ausdruck ohne expliziten Output-Spaltennamen. Dadurch entsteht die Portabilitaetswarnung `PORT_COL_NAME`.

## Beispiel 8

- `entry_index`: `12`
- `db_id`: `student_assessment`
- gematchter Prompt: `1`
- Lint-Detail: `[{"code": "PORT_COL_NAME", "description": "Implicit col might not be portable"}]`

### SQL Query

```sql
SELECT p.`first_name`, p.`last_name` FROM `People` AS p WHERE NOT EXISTS(SELECT 1 FROM `People` AS p2 WHERE p2.`first_name` = 'John' AND p2.`person_id` = p.`person_id`)
```

### Schema

- **Addresses**(address_id INTEGER, line_1 VARCHAR, line_2 VARCHAR, city VARCHAR, zip_postcode CHAR, state_province_county VARCHAR, country VARCHAR)
- **People**(person_id INTEGER, first_name VARCHAR, middle_name VARCHAR, last_name VARCHAR, cell_mobile_number VARCHAR, email_address VARCHAR, login_name VARCHAR, password VARCHAR)
- **Students**(student_id INTEGER, student_details VARCHAR)
- **Courses**(course_id VARCHAR, course_name VARCHAR, course_description VARCHAR, other_details VARCHAR)
- **People_Addresses**(person_address_id INTEGER, person_id INTEGER, address_id INTEGER, date_from DATETIME, date_to DATETIME)
- **Student_Course_Registrations**(student_id INTEGER, course_id INTEGER, registration_date DATETIME)
- **Student_Course_Attendance**(student_id INTEGER, course_id INTEGER, date_of_attendance DATETIME)
- **Candidates**(candidate_id INTEGER, candidate_details VARCHAR)
- **Candidate_Assessments**(candidate_id INTEGER, qualification CHAR, assessment_date DATETIME, asessment_outcome_code CHAR)


### Primary Keys

- Addresses: address_id
- People: person_id
- Students: student_id
- Courses: course_id
- People_Addresses: person_address_id
- Student_Course_Registrations: student_id, course_id
- Student_Course_Attendance: student_id, course_id
- Candidates: candidate_id
- Candidate_Assessments: candidate_id, qualification


### Foreign Keys

- Students.student_id = People.person_id
- People_Addresses.person_id = People.person_id
- People_Addresses.address_id = Addresses.address_id
- Student_Course_Registrations.student_id = Students.student_id
- Student_Course_Registrations.course_id = Courses.course_id
- Student_Course_Attendance.student_id, Student_Course_Attendance.course_id = Student_Course_Registrations.student_id, Student_Course_Registrations.course_id
- Candidates.candidate_id = People.person_id
- Candidate_Assessments.candidate_id = Candidates.candidate_id


### Sample Rows (Auszug)

**Addresses**
- `{"address_id": 73, "line_1": "67831 Lavonne Lodge\nOlsontown, DC 20894", "line_2": "Apt. 756", "city": "Alizeshire", "zip_postcode": "687", "state_province_county": "NewMexico", "country": "USA"}`
- `{"address_id": 45, "line_1": "242 Pacocha Streets\nEast Isabellashire, ND 03506", "line_2": "Suite 370", "city": "O'Connellview", "zip_postcode": "514", "state_province_county": "NewMexico", "country": "USA"}`
**People**
- `{"person_id": 151, "first_name": "Hoyt", "middle_name": "Mercedes", "last_name": "Wintheiser", "cell_mobile_number": "1-603-110-0647", "email_address": "stanley.monahan@example.org", "login_name": "bnto", "password": "c55795df86182959094b83e27900f7cf44ced570"}`
- `{"person_id": 111, "first_name": "Shannon", "middle_name": "Elissa", "last_name": "Senger", "cell_mobile_number": "01955267735", "email_address": "javier.trantow@example.net", "login_name": "pgub", "password": "5e4ff49a61b3544da3ad7dc7e2cf28847564c64c"}`
**Students**
- `{"student_id": 151, "student_details": "John"}`
- `{"student_id": 181, "student_details": "Nancy"}`


### Warum PORT_COL_NAME hier wahrscheinlich ausgeloest wird

Die Query verwendet in einer `NOT EXISTS`-Subquery `SELECT 1`. Das ist SQL-semantisch ueblich, aber SQLLint betrachtet die Konstante `1` als SELECT-Ausdruck ohne expliziten Output-Spaltennamen. Dadurch entsteht die Portabilitaetswarnung `PORT_COL_NAME`.

## Beispiel 9

- `entry_index`: `15`
- `db_id`: `bike_1`
- gematchter Prompt: `1`
- Lint-Detail: `[{"code": "PORT_COL_NAME", "description": "Implicit col might not be portable"}]`

### SQL Query

```sql
SELECT s.`id`, s.`name` FROM `station` AS s WHERE NOT EXISTS(SELECT 1 FROM `status` AS st WHERE st.`station_id` = s.`id`)
```

### Schema

- **station**(id INTEGER, name TEXT, lat NUMERIC, long NUMERIC, dock_count INTEGER, city TEXT, installation_date TEXT)
- **status**(station_id INTEGER, bikes_available INTEGER, docks_available INTEGER, time TEXT)
- **trip**(id INTEGER, duration INTEGER, start_date TEXT, start_station_name TEXT, start_station_id INTEGER, end_date TEXT, end_station_name TEXT, end_station_id INTEGER, bike_id INTEGER, subscription_type TEXT, zip_code INTEGER)
- **weather**(date TEXT, max_temperature_f INTEGER, mean_temperature_f INTEGER, min_temperature_f INTEGER, max_dew_point_f INTEGER, mean_dew_point_f INTEGER, min_dew_point_f INTEGER, max_humidity INTEGER, mean_humidity INTEGER, min_humidity INTEGER, max_sea_level_pressure_inches NUMERIC, mean_sea_level_pressure_inches NUMERIC, min_sea_level_pressure_inches NUMERIC, max_visibility_miles INTEGER, mean_visibility_miles INTEGER, min_visibility_miles INTEGER, max_wind_Speed_mph INTEGER, mean_wind_speed_mph INTEGER, max_gust_speed_mph INTEGER, precipitation_inches INTEGER, cloud_cover INTEGER, events TEXT, wind_dir_degrees INTEGER, zip_code INTEGER)


### Primary Keys

- station: id
- status: none
- trip: id
- weather: none


### Foreign Keys

- status.station_id = station.id


### Sample Rows (Auszug)

**station**
- `{"id": 69, "name": "San Francisco Caltrain 2 (330 Townsend)", "lat": 37.7766, "long": -122.39546999999999, "dock_count": 23, "city": "San Francisco", "installation_date": "8/23/2013"}`
- `{"id": 24, "name": "Redwood City Public Library", "lat": 37.484219, "long": -122.227424, "dock_count": 15, "city": "Redwood City", "installation_date": "8/12/2013"}`
**status**
- `{"station_id": 7, "bikes_available": 5, "docks_available": 10, "time": "2015-06-02 14:32:02"}`
- `{"station_id": 71, "bikes_available": 10, "docks_available": 9, "time": "2015-06-02 14:41:02"}`
**trip**
- `{"id": 908781, "duration": 519, "start_date": "8/27/2015 18:01", "start_station_name": "Embarcadero at Sansome", "start_station_id": 60, "end_date": "8/27/2015 18:09", "end_station_name": "Harry Bridges Plaza (Ferry Building)", "end_station_id": 50, "bike_id": 416, "subscription_type": "Subscriber", "zip_code": 94122}`
- `{"id": 908720, "duration": 600, "start_date": "8/27/2015 17:46", "start_station_name": "Broadway St at Battery St", "start_station_id": 82, "end_date": "8/27/2015 17:56", "end_station_name": "Market at Sansome", "end_station_id": 77, "bike_id": 630, "subscription_type": "Subscriber", "zip_code": 94109}`


### Warum PORT_COL_NAME hier wahrscheinlich ausgeloest wird

Die Query verwendet in einer `NOT EXISTS`-Subquery `SELECT 1`. Das ist SQL-semantisch ueblich, aber SQLLint betrachtet die Konstante `1` als SELECT-Ausdruck ohne expliziten Output-Spaltennamen. Dadurch entsteht die Portabilitaetswarnung `PORT_COL_NAME`.

## Beispiel 10

- `entry_index`: `16`
- `db_id`: `bike_1`
- gematchter Prompt: `1`
- Lint-Detail: `[{"code": "PORT_COL_NAME", "description": "Implicit col might not be portable"}]`

### SQL Query

```sql
SELECT `trip`.`id`, `trip`.`duration`, `trip`.`start_date`, `trip`.`start_station_name`, `trip`.`end_date`, `trip`.`end_station_name`, `trip`.`bike_id`, `trip`.`subscription_type`, `trip`.`zip_code` FROM `trip` WHERE NOT EXISTS(SELECT 1 FROM `trip` AS t WHERE t.`id` = `trip`.`id` AND t.`subscription_type` = 'Subscriber')
```

### Schema

- **station**(id INTEGER, name TEXT, lat NUMERIC, long NUMERIC, dock_count INTEGER, city TEXT, installation_date TEXT)
- **status**(station_id INTEGER, bikes_available INTEGER, docks_available INTEGER, time TEXT)
- **trip**(id INTEGER, duration INTEGER, start_date TEXT, start_station_name TEXT, start_station_id INTEGER, end_date TEXT, end_station_name TEXT, end_station_id INTEGER, bike_id INTEGER, subscription_type TEXT, zip_code INTEGER)
- **weather**(date TEXT, max_temperature_f INTEGER, mean_temperature_f INTEGER, min_temperature_f INTEGER, max_dew_point_f INTEGER, mean_dew_point_f INTEGER, min_dew_point_f INTEGER, max_humidity INTEGER, mean_humidity INTEGER, min_humidity INTEGER, max_sea_level_pressure_inches NUMERIC, mean_sea_level_pressure_inches NUMERIC, min_sea_level_pressure_inches NUMERIC, max_visibility_miles INTEGER, mean_visibility_miles INTEGER, min_visibility_miles INTEGER, max_wind_Speed_mph INTEGER, mean_wind_speed_mph INTEGER, max_gust_speed_mph INTEGER, precipitation_inches INTEGER, cloud_cover INTEGER, events TEXT, wind_dir_degrees INTEGER, zip_code INTEGER)


### Primary Keys

- station: id
- status: none
- trip: id
- weather: none


### Foreign Keys

- status.station_id = station.id


### Sample Rows (Auszug)

**station**
- `{"id": 69, "name": "San Francisco Caltrain 2 (330 Townsend)", "lat": 37.7766, "long": -122.39546999999999, "dock_count": 23, "city": "San Francisco", "installation_date": "8/23/2013"}`
- `{"id": 24, "name": "Redwood City Public Library", "lat": 37.484219, "long": -122.227424, "dock_count": 15, "city": "Redwood City", "installation_date": "8/12/2013"}`
**status**
- `{"station_id": 7, "bikes_available": 5, "docks_available": 10, "time": "2015-06-02 14:32:02"}`
- `{"station_id": 71, "bikes_available": 10, "docks_available": 9, "time": "2015-06-02 14:41:02"}`
**trip**
- `{"id": 908781, "duration": 519, "start_date": "8/27/2015 18:01", "start_station_name": "Embarcadero at Sansome", "start_station_id": 60, "end_date": "8/27/2015 18:09", "end_station_name": "Harry Bridges Plaza (Ferry Building)", "end_station_id": 50, "bike_id": 416, "subscription_type": "Subscriber", "zip_code": 94122}`
- `{"id": 908720, "duration": 600, "start_date": "8/27/2015 17:46", "start_station_name": "Broadway St at Battery St", "start_station_id": 82, "end_date": "8/27/2015 17:56", "end_station_name": "Market at Sansome", "end_station_id": 77, "bike_id": 630, "subscription_type": "Subscriber", "zip_code": 94109}`


### Warum PORT_COL_NAME hier wahrscheinlich ausgeloest wird

Die Query verwendet in einer `NOT EXISTS`-Subquery `SELECT 1`. Das ist SQL-semantisch ueblich, aber SQLLint betrachtet die Konstante `1` als SELECT-Ausdruck ohne expliziten Output-Spaltennamen. Dadurch entsteht die Portabilitaetswarnung `PORT_COL_NAME`.
