# Chip reset failure response

Status: qualified candidate; production and standalone delivery acceptance pending.

The supported `dx11_260923` build sends `202/BBC` for chip reset. Previously the chip handler returned no response. It now returns `201/BBD`, result 2005 plus an empty inventory vector. The original consumer reads both fields before handling a failure, so the payload is eight bytes: `000007d500000000`.

This branch is failure-only in every phase and switch state. It does not inspect the request body, account, inventory or database. Other namespaces/builds and the existing BB8 tuning and mode15 installation paths retain their behavior. No schema, client, launcher, calculation, effect, timer or interface changes are included.

Actual reset remains disabled. The post-reset raw probability byte, preservation or reroll of base option identities, and reset ED rule are unresolved. No fee, voucher consumption, quota, successful reset or reset transaction is implemented.

Five private dispatcher/state-preservation groups passed before this Git preparation; those successful checks were reused. The bounded original BBD failure parser evidence was also reused. Natural player UI, complete wait removal and actual reset acceptance are not claimed.

Run the resource-free routing checks with `python -B tools/check_chip_reset_failure.py`. They verify the complete failure body, protocol codec, no player-state access, namespace/build isolation and unchanged BB8 transaction routing without opening a database, network connection or game. Standard source/privacy checks remain `python -B tools/ci_checks.py`.

Qualified source SHA256:

- `els_server/domain/equipment_chip_flow.py`: `549a34af48aaa606040f178e57d0cba8b4855847c6c0adcbc2b6e946621010e5`
- `els_server/protocol/equipment_chip_messages.py`: `59ff6e69de483dff6974920a5f706752c4c16062db3bfc80c7b8b14d5f6cc483`
