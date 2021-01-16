# Bigtable Automation

BT automation works as follows:

1.  The Prophet Generator Borg job notifies a
    [Cloud Function](https://pantheon.corp.google.com/functions/details/us-central1/prophet-cache-trigger?project=google.com:datcom-store-dev&tab=general)
    (GCF)
    which creates a new BT table, scales up BT resources (for base cache builds
    only) and kicks off the
    [CSV-to-BT Dataflow job](https://pantheon.corp.google.com/dataflow/jobs?organizationId=433637338589&project=google.com:datcom-store-dev)
    stored in
    [datcom-dataflow-templates](https://pantheon.corp.google.com/storage/browser/_details/datcom-dataflow-templates/templates/csv_to_bt_improved).

2.  When the Dataflow job completes, it notifies the same cloud function to
    scale down BT resources (for base cache builds only).

3.  The notifications between Borg-to-GCF and Dataflow-to-GCF happen using
    per-version state files located in GCS:

    *   Base cache:
        [/bigstore/automation_control/base/{BT_Table}/...](https://pantheon.corp.google.com/storage/browser/automation_control/base)
    *   Branch cache:
        [/bigstore/automation_control/branch/{BT_Table}/...](https://pantheon.corp.google.com/storage/browser/automation_control/branch)

    Borg job sets `init`, then GCF on launching the Dataflow job sets `launched`
    and Dataflow job on completion sets `completed`.

4.  The Borg job polls for a fixed timeout on the `launched` and `completed`
    state files to track progress and completion.

## [Cloud Function](gcf/README.md)

## [Dataflow Job](java/dataflow/README.md)
