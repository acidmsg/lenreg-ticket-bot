# appointment_list

**Endpoint:** `POST https://zdrav.lenreg.ru/api/appointment_list/`
**Purpose:** Получение списка доступных слотов (талонов) для конкретного врача.

## Parameters

| Parameter                      | Type   | Required | Description                |
| ------------------------------ | ------ | -------- | -------------------------- |
| `doctor_form-doctor_id`        | string | yes      | ID врача                   |
| `doctor_form-clinic_id`        | string | yes      | ID поликлиники             |
| `doctor_form-patient_id`       | string | yes      | ID пациента                |
| `doctor_form-history_id`       | string | no       | ID истории (пустая строка) |
| `doctor_form-appointment_type` | string | no       | Тип записи (пустая строка) |

## Response

```json
{
  "response": {
    "2026-05-19": [
      {
        "id": "41814720000",
        "date_start": {
          "year": "2026",
          "day_verbose": "Втр",
          "month": "05",
          "month_verbose": "Май",
          "time": "14:40",
          "iso": "2026-05-19T14:40:00",
          "day": "19"
        },
        "date_end": {
          "year": "2026",
          "day_verbose": "Втр",
          "month": "05",
          "month_verbose": "Май",
          "time": "15:00",
          "iso": "2026-05-19T15:00:00",
          "day": "19"
        }
      }
    ]
  },
  "success": true,
  "error": {}
}
```

## Payload

```json
{
  "doctor_form-doctor_id": "34333",
  "doctor_form-clinic_id": "271",
  "doctor_form-patient_id": "2343192",
  "doctor_form-history_id": "",
  "doctor_form-appointment_type": ""
}
```

## CURL

```bash
curl 'https://zdrav.lenreg.ru/api/appointment_list/' \
  -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
  -b 'csrftoken=NOTPROVIDED' \
  -H 'Origin: https://zdrav.lenreg.ru' \
  -H 'Referer: https://zdrav.lenreg.ru/signup/free/' \
  -H 'X-Requested-With: XMLHttpRequest' \
  --data-raw 'doctor_form-doctor_id=25444&doctor_form-clinic_id=272&doctor_form-patient_id=2343192&doctor_form-history_id=&doctor_form-appointment_type='
```
