# speciality_list

**Endpoint:** `POST https://zdrav.lenreg.ru/api/speciality_list/`
**Purpose:** Получение списка специальностей врачей для заданной поликлиники и пациента.

## Parameters

| Parameter                | Type   | Required | Description                |
| ------------------------ | ------ | -------- | -------------------------- |
| `clinic_form-clinic_id`  | string | yes      | ID поликлиники             |
| `clinic_form-patient_id` | string | yes      | ID пациента                |
| `clinic_form-history_id` | string | no       | ID истории (пустая строка) |

## Response

```json
{
  "response": [
    {
      "NameSpesiality": "Стоматология профилактическая",
      "FerIdSpesiality": "233",
      "IdSpesiality": "53145",
      "CountFreeTicket": 23,
      "LastDate": {
        "year": "2026",
        "day_verbose": "Втр",
        "month": "05",
        "month_verbose": "Май",
        "time": "14:40",
        "iso": "2026-05-19T14:40:00",
        "day": "19"
      },
      "NearestDate": {
        "year": "2026",
        "day_verbose": "Пнд",
        "month": "05",
        "month_verbose": "Май",
        "time": "11:40",
        "iso": "2026-05-18T11:40:00",
        "day": "18"
      },
      "CountFreeParticipantIE": 23
    }
  ],
  "success": true,
  "error": {}
}
```

## CURL

```bash
curl 'https://zdrav.lenreg.ru/api/speciality_list/' \
  -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
  -b 'csrftoken=NOTPROVIDED' \
  -H 'Origin: https://zdrav.lenreg.ru' \
  -H 'Referer: https://zdrav.lenreg.ru/signup/free/' \
  -H 'X-CSRFToken: NOTPROVIDED' \
  -H 'X-Requested-With: XMLHttpRequest' \
  --data-raw 'clinic_form-clinic_id=272&clinic_form-history_id=&clinic_form-patient_id=2343192'
```
