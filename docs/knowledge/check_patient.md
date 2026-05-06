# check_patient

## CURL

```bash
curl 'https://zdrav.lenreg.ru/api/check_patient/' \
  -H 'Accept: */*' \
  -H 'Accept-Language: ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7' \
  -H 'Cache-Control: no-cache' \
  -H 'Connection: keep-alive' \
  -H 'Content-Type: application/x-www-form-urlencoded; charset=UTF-8' \
  -b 'csrftoken=NOTPROVIDED' \
  -H 'DNT: 1' \
  -H 'Origin: https://zdrav.lenreg.ru' \
  -H 'Pragma: no-cache' \
  -H 'Referer: https://zdrav.lenreg.ru/signup/free/' \
  -H 'Sec-Fetch-Dest: empty' \
  -H 'Sec-Fetch-Mode: cors' \
  -H 'Sec-Fetch-Site: same-origin' \
  -H 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36' \
  -H 'X-Requested-With: XMLHttpRequest' \
  -H 'sec-ch-ua: "Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"' \
  -H 'sec-ch-ua-mobile: ?0' \
  -H 'sec-ch-ua-platform: "Windows"' \
  -H 'sec-gpc: 1' \
  --data-raw 'patient_form-first_name=%D0%90%D1%80%D1%82%D1%91%D0%BC&patient_form-last_name=%D0%9A%D0%B0%D0%B7%D0%B0%D0%BD%D0%BE%D0%B2%D1%81%D0%BA%D0%B8%D0%B9&patient_form-middle_name=%D0%98%D0%B3%D0%BE%D1%80%D0%B5%D0%B2%D0%B8%D1%87&patient_form-insurance_series=&patient_form-insurance_number=&patient_form-birthday=1990-07-05T00%3A00%3A00.000Z&patient_form-clinic_id=272&csrfmiddlewaretoken=NOTPROVIDED'
```

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
