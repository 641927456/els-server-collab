# Native CP coexistence regression

`verify_native_CP_coexist.py` is the exact final executed owned-process ABI fixture. It preserves existing dispatcher, encoder and calculator entry observers; checks four request forms, nested sends, current owner, vector restoration, disposal/reload, failure refusal and untouched-body pin rejection. It creates and closes only its own short-lived Python process.

Maintainer invocation on the pinned Windows workspace:

```
python -B verify_native_CP_coexist.py --candidate <fully-qualified-runtime-root> --tag=-review
```

The test requires Frida and the fixed executable memory image at the existing G:/els analysis resource path. That binary input is separately hash-locked and deliberately absent from Git. Full Application/TLS and SQL regression inputs are retained by the maintainer at G:/els/analysis/five-session-integration-20261107-v1/test-fixtures; their sanitized results and scope are in review/validation.json. No production connection, player database, GUI input or natural combat is used by this fixture.
