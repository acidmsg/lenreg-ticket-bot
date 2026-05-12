# check_patient

**Endpoint:** `POST https://zdrav.lenreg.ru/api/check_patient/`
**Purpose:** Поиск пациента по ФИО и дате рождения в указанной поликлинике.

## Parameters

| Parameter                       | Type   | Required | Description            |
| ------------------------------- | ------ | -------- | ---------------------- |
| `patient_form-first_name`       | string | yes      | Имя (URL-encoded)      |
| `patient_form-last_name`        | string | yes      | Фамилия (URL-encoded)  |
| `patient_form-middle_name`      | string | yes      | Отчество (URL-encoded) |
| `patient_form-birthday`         | string | yes      | Дата рождения ISO 8601 |
| `patient_form-clinic_id`        | string | yes      | ID поликлиники         |
| `patient_form-insurance_series` | string | no       | Серия полиса           |
| `patient_form-insurance_number` | string | no       | Номер полиса           |
| `csrfmiddlewaretoken`           | string | yes      | CSRF-токен             |

## Response

```json
{
  "response": {
    "history_id": null,
    "patient_id": "2343192"
  },
  "success": true,
  "error": {}
}
```

## CURL

```bash
curl 'https://zdrav.lenreg.ru/api/check_patient/' \
  -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
  -b 'csrftoken=NOTPROVIDED' \
  -H 'Origin: https://zdrav.lenreg.ru' \
  -H 'Referer: https://zdrav.lenreg.ru/signup/free/' \
  -H 'X-Requested-With: XMLHttpRequest' \
  --data-raw 'patient_form-first_name=%D0%90%D1%80%D1%82%D1%91%D0%BC&patient_form-last_name=%D0%9A%D0%B0%D0%B7%D0%B0%D0%BD%D0%BE%D0%B2%D1%81%D0%BA%D0%B8%D0%B9&patient_form-middle_name=%D0%98%D0%B3%D0%BE%D1%80%D0%B5%D0%B2%D0%B8%D1%87&patient_form-birthday=1990-07-05T00%3A00%3A00.000Z&patient_form-clinic_id=272&csrfmiddlewaretoken=NOTPROVIDED'
```
