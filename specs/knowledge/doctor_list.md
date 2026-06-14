# doctor_list

**Endpoint:** `POST https://zdrav.lenreg.ru/api/doctor_list/`
**Purpose:** Получение списка врачей по специальности в заданной поликлинике.

## Parameters

| Parameter                       | Type   | Required | Description                |
| ------------------------------- | ------ | -------- | -------------------------- |
| `speciality_form-speciality_id` | string | yes      | ID специальности           |
| `speciality_form-clinic_id`     | string | yes      | ID поликлиники             |
| `speciality_form-patient_id`    | string | yes      | ID пациента                |
| `speciality_form-history_id`    | string | no       | ID истории (пустая строка) |

## Response

```json
{
  "response": [
    {
      "AriaNumber": null,
      "Name": "Каледин Денис Александрович",
      "IdDoc": "25444",
      "CountFreeTicket": 4,
      "LastDate": {
        "year": "2026",
        "day_verbose": "Втр",
        "month": "05",
        "month_verbose": "Май",
        "time": "16:20",
        "iso": "2026-05-19T16:20:00",
        "day": "19"
      },
      "NearestDate": {
        "year": "2026",
        "day_verbose": "Втр",
        "month": "05",
        "month_verbose": "Май",
        "time": "14:40",
        "iso": "2026-05-19T14:40:00",
        "day": "19"
      },
      "CountFreeParticipantIE": 4
    }
  ],
  "success": true,
  "error": {}
}
```

## CURL

```bash
curl 'https://zdrav.lenreg.ru/api/doctor_list/' \
  -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
  -b 'csrftoken=NOTPROVIDED' \
  -H 'Origin: https://zdrav.lenreg.ru' \
  -H 'Referer: https://zdrav.lenreg.ru/signup/free/' \
  -H 'X-Requested-With: XMLHttpRequest' \
  --data-raw 'speciality_form-speciality_id=53061&speciality_form-clinic_id=272&speciality_form-patient_id=2343192&speciality_form-history_id='
```
