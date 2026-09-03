from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.proposal_participant_sync import PROPOSAL_PARTICIPANT_SYNC_FIELDS

if TYPE_CHECKING:
    from app.models.participant import Participant
    from app.models.proposal_participant import ProposalParticipant


PROPOSAL_PARTICIPANT_SNAPSHOT_FIELDS = frozenset(
    PROPOSAL_PARTICIPANT_SYNC_FIELDS
)


class ProposalParticipantSnapshotView:
    def __init__(
        self,
        participant: Participant,
        proposal_participant: ProposalParticipant,
    ) -> None:
        self._participant = participant
        self._proposal_participant = proposal_participant

    def __getattr__(self, field_name: str):
        if field_name in PROPOSAL_PARTICIPANT_SNAPSHOT_FIELDS:
            return getattr(self._proposal_participant, field_name)
        return getattr(self._participant, field_name)


def participant_snapshot_view(
    participant: Participant,
    proposal_participant: ProposalParticipant | None,
):
    if proposal_participant is None:
        return participant
    return ProposalParticipantSnapshotView(participant, proposal_participant)
