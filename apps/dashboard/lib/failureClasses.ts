// Human descriptions of the AOIE failure taxonomy (engine/models/enums.py::FailureClass).

export interface FailureClassInfo {
  id: string;
  label: string;
  description: string;
}

export const FAILURE_CLASSES: FailureClassInfo[] = [
  {
    id: "UI_FALSE_COMPLETION",
    label: "UI False Completion",
    description:
      "The UI / DOM reported success but the authoritative backend source (API or DB) shows the state never changed. The canonical 'agent lied' signature.",
  },
  {
    id: "PERSISTENCE_FAILURE",
    label: "Persistence Failure",
    description:
      "The mutation appeared to run but was never durably written — the record is unchanged when read back from the source of truth.",
  },
  {
    id: "BACKEND_FAILURE",
    label: "Backend Failure",
    description:
      "The backend rejected or dropped the mutation; no persisted effect could be verified.",
  },
  {
    id: "WRONG_TARGET",
    label: "Wrong Target",
    description:
      "A change was persisted, but on the wrong record/entity — the intended target is untouched.",
  },
  {
    id: "WRONG_VALUE",
    label: "Wrong Value",
    description:
      "A value was persisted to the correct target, but it is wrong or mangled versus what the task required.",
  },
  {
    id: "PARTIAL_EXECUTION",
    label: "Partial Execution",
    description:
      "Some postconditions were satisfied while others were not — the task only half-completed.",
  },
  {
    id: "AUTH_FAILURE",
    label: "Auth Failure",
    description:
      "The mutation was rejected for authentication/authorization reasons (e.g. 401); nothing changed.",
  },
  {
    id: "TIMEOUT",
    label: "Timeout",
    description:
      "The operation stalled past the client/agent timeout window; the outcome could not be confirmed in time.",
  },
  {
    id: "NETWORK_FAILURE",
    label: "Network Failure",
    description:
      "A network-layer error prevented the mutation from reaching or completing on the backend.",
  },
  {
    id: "STALE_STATE",
    label: "Stale State",
    description:
      "The write persisted, but authoritative reads returned a stale (pre-write) value — read-after-write inconsistency.",
  },
  {
    id: "STATE_CONFLICT",
    label: "State Conflict",
    description:
      "Independent verifier sources disagree in a way that cannot be reconciled — conflicting observations of the same state.",
  },
  {
    id: "EXTERNAL_DEPENDENCY_FAILURE",
    label: "External Dependency Failure",
    description:
      "A downstream/external dependency the task relied on failed, blocking a verifiable outcome.",
  },
  {
    id: "VERIFICATION_FAILURE",
    label: "Verification Failure",
    description:
      "AOIE itself could not gather enough evidence to reach a verdict — an inconclusive verification, not a task failure per se.",
  },
];

const BY_ID: Record<string, FailureClassInfo> = Object.fromEntries(
  FAILURE_CLASSES.map((f) => [f.id, f]),
);

export function failureInfo(id: string): FailureClassInfo {
  return (
    BY_ID[id] ?? {
      id,
      label: id,
      description: "No description available for this failure class.",
    }
  );
}
