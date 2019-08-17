TEST_USER_AGENT = "python-trio/snekomatic testing"

# These are the credentials for a real github app called "snekomatic-test",
# which is locked down to have read-only access only, on
# "njsmith-test-org/test-repo", an organization and repository that contain
# nothing of value. But it's useful for end-to-end testing of our GH API code!
TEST_APP_ID = "38758"
TEST_WEBHOOK_SECRET = "DQUSgKV8K-WnMj3TIRgzEBlnuEPe09rQ2VeKA8K7lZ4"
TEST_PRIVATE_KEY = """
-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA3QWdNvdcKJAZ5Ap3Gm2YH3NmJjNyITgBpzY58ysOUabzqWBp
Zv6Ugq2JennefeEWz3x8/Cp8XEGHleuJCCRUsKCGj7lJf+fXdxZ53+RRdfYgjy5Y
P3pPOqT3ltjUZg75Msd4jNyoUwzUPpcK7N5l8XlCWKdYSfdNnmo9MWy0lrPMXU1v
3Ic0PRvdWD9+QncE64su9qgzTzGEayA1FwCX+M4dNKoX0qQWVeTcraNaZSrTTYE1
9oC/9aeMWQA87DCbtffzZzFPw8rz5L7vhtZvxpFeGQrgZ50da4MkSuxyr27Ab0wx
yLtPhVFxUUUWHzZTqhm9qVm5pIJ8f+RGL+q0aQIDAQABAoIBAQC0dFT7/9IavCyn
Z3P+++PsKcgJAI/6V0PiRf/ibhDu0aS3caQdF1Yhq5ZHjSD/HbwGA9n3+Kg4mrgc
y4XCRAdxfl7fEaTU7XGaJZu0FTH9YcsLnAcpLK9rbi1H2Bjyit8jeoEOYUp9JEhW
IfQlmR8anKpyv47yNRwGby8vH1YCg51eQPBirBNMqbP20cAW7rDk8Tz3TBiqBLsP
5rfvr+LVEMJ9y3kzZuIdFnrUUtfNEExnAeVw4f4THs7SyuFHn/iESTJWNaoNxY10
ciXj6RwQFCXzflTL1AUO5RiSvvXNBFVicSUEoHPGnuPnMruvxK/qroh0N24P9Qdc
9sSFJtNRAoGBAPgj3PR6EwgMixaUebpiO4mwwv+nGW+M0e8Bz9iUd2g9/f7U+fkN
uy2xCN5yYdsH6MII8yxbDaV6kcyMdnWRuko9KJ9zLcstylC81hB369KmwADOUl1I
BBbPeoupzsuw/6ox9/QXMO7+Ji6tCSQ1xFJyoz5Hzh9YBqIcbOGFk8XfAoGBAOQF
2m7GYv87i6nsGxWlfJF4DKsM1wIeIVMiw+ToxLEEVyxBWI13AFhAxK8paW+/qWbp
H/Ud8yMbPbLav8PIJr6cYMJSK1xN+LL0Kgq4RHaw282+mI0t6Jg2Itrr+7gfNLnG
HE4fvs+4ZYV6bPYDszAgELq7W3sIA8nrwJE3q/63AoGADQZU4sBFn3aJFnZUrWPa
nC+bDLBItYI+wrzlnAiu+9nFK0sik+AUoyFXxdVbLZQMs6KkoP9mh/kXDhWRYjpz
/NGZAEWbcb7Fj9dZpSOmTThTe7dYu2y8SjY5yHrxT9/Ki7Rzv2w4NVNBzdFnWW85
DtrVlr9OIncMYhX74RqR1yECgYAQHp3PgPTUqEf6Tjen8xf4TK1QlkrI2opujyGc
GBx3iyACf+gbsBL1Kjb9TwcmID2AifB5apGapL1a3H38ADVE+lcYxahNETIIrJwg
P+CPJ3eSduvf5yPvRrx2D4KvBH28uFWd7D6X/qgmpH35ck+DknC8Uqxn6SwjZSgq
2+2rxwKBgQDc2Xf6lJZkUNltH8yRw7WcIU0FyUAFHwMYc9IBaNudL47d9zq5/xiU
e8jTxtp/VIfaRDKa4ZM5MDAoZ/6OvKe+KwMWT8NBW6LTKc2QZRtJ6WVD1FH6kaTZ
9N78paKFQFvwHb3vXpKci0WhxYmvaUqKORJt9JuCefJcdDCk7nKk0A==
-----END RSA PRIVATE KEY-----
"""
# You can find this magic number by looking at the end of this URL:
# https://github.com/organizations/python-trio/settings/installations/1541311
# (It's also available by querying the /app/installations endpoint)
TEST_INSTALLATION_ID = "1541311"
