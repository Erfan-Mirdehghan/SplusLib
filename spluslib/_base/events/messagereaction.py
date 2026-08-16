from .common import EventBuilder, EventCommon, name_inner_event
from .. import utils
from ..tl import types


@name_inner_event
class MessageReaction(EventBuilder):
    """
    Occurs whenever the reactions on a message change (someone reacts,
    removes a reaction, or the reaction counts otherwise update).

    .. note::

        SoroushPlus only tells you the *current totals* per emoji on
        the message, not "user X just added emoji Y" as a discrete
        event. If ``recent_reactions`` is available in the update (it
        usually is for small/medium reaction counts), `added_by` and
        `reactions` below let you see who's behind the most recent
        ones; for the full picture use `get_message_reactions()` /
        `event.get_reactions()`.

    Example
        .. code-block:: python

            from spluspy import events

            @client.on(events.MessageReaction)
            async def handler(event):
                print('Message', event.msg_id, 'now has', event.total_count, 'reactions')
                for peer, emoji in event.added_by:
                    print(' -', peer, 'reacted with', emoji)
    """
    def __init__(self, chats=None, *, blacklist_chats=False, func=None):
        super().__init__(chats, blacklist_chats=blacklist_chats, func=func)

    @classmethod
    def build(cls, update, others=None, self_id=None):
        if isinstance(update, types.UpdateMessageReactions):
            return cls.Event(update.peer, update.msg_id, update.reactions)

    class Event(EventCommon):
        """
        Represents the event of a message's reactions changing.

        Members:
            msg_id (`int`):
                The ID of the message whose reactions changed.

            reactions (`MessageReactions <spluspy.tl.types.MessageReactions>`):
                The raw reactions object: has ``.results`` (list of
                ``ReactionCount``, one per distinct emoji used, each
                with ``.reaction`` and ``.count``) and
                ``.recent_reactions`` (list of ``MessagePeerReaction``,
                who reacted most recently and with what, when known).
        """
        def __init__(self, peer, msg_id, reactions):
            super().__init__(chat_peer=peer, msg_id=msg_id)
            self.msg_id = msg_id
            self.reactions = reactions
            self._message = None

        @property
        def total_count(self):
            """Total number of reactions across all emoji on this message."""
            return sum(r.count for r in (self.reactions.results or []))

        @property
        def added_by(self):
            """
            List of ``(peer_id, emoji_or_reaction)`` tuples for the
            most recent reactors, when the server included that
            detail (``reactions.recent_reactions``). May be empty even
            if the message has reactions -- SoroushPlus doesn't always
            send this for larger reaction counts.
            """
            result = []
            for r in (self.reactions.recent_reactions or []):
                emoji = r.reaction.emoticon if hasattr(r.reaction, 'emoticon') else str(r.reaction)
                result.append((utils.get_peer_id(r.peer_id), emoji))
            return result

        async def get_message(self):
            """Fetches and returns the `Message <spluspy.tl.custom.message.Message>` this reaction is on."""
            if self._message is None:
                chat = await self.get_input_chat()
                if chat:
                    self._message = await self._client.get_messages(chat, ids=self.msg_id)
            return self._message

        async def get_reactions(self):
            """
            Re-fetches the full, current reaction breakdown for this
            message (equivalent to bot.get_reactions(chat_id, msg_id)).
            Prefer this over `reactions` if you need up-to-the-moment
            counts, since this event may have coalesced multiple rapid
            reaction changes into one update.
            """
            chat = await self.get_input_chat()
            if not chat:
                return []
            from ..tl import functions
            result = await self._client(functions.messages.GetMessagesReactionsRequest(
                peer=chat, id=[self.msg_id],
            ))
            if not result.updates:
                return []
            return result.updates[0].reactions.results
