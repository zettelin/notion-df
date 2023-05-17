from __future__ import annotations as _

from abc import ABCMeta, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any, Literal, final, Sequence, Iterable
from uuid import UUID

from typing_extensions import Self

from notion_df.object.common import DateRange, Annotations
from notion_df.util.collection import FinalClassDict
from notion_df.util.serialization import DualSerializable, deserialize, serialize


class RichTextSpan(DualSerializable, metaclass=ABCMeta):
    # https://developers.notion.com/reference/rich-text
    annotations: Optional[Annotations]
    """
    Note: when updating block texts,
    * set `None` (the default value) to retain the current annotations.
    * set `Annotations()` to remove the annotations and make a plain text.
    """
    plain_text: Optional[str]
    href: Optional[str]

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        rich_text_span_registry[cls.get_typename()] = cls

    def serialize(self) -> dict[str, Any]:
        serialized = self._serialize_main()
        if self.annotations:
            serialized['annotations'] = self.annotations.serialize()
        return serialized

    @abstractmethod
    def _serialize_main(self) -> dict[str, Any]:
        pass

    @classmethod
    @abstractmethod
    def get_typename(cls) -> tuple[str, ...]:
        pass

    @classmethod
    @abstractmethod
    def _deserialize_main(cls, serialized: dict[str, Any]) -> Self:
        pass

    @classmethod
    @final
    def _deserialize_this(cls, serialized: dict[str, Any]) -> Self:
        self = cls._deserialize_main(serialized)
        self.annotations = Annotations.deserialize(serialized['annotations'])
        self.plain_text = serialized['plain_text']
        self.href = serialized['href']
        return self

    @classmethod
    @final
    def deserialize(cls, serialized: dict[str, Any]) -> Self:
        if cls != RichTextSpan:
            return cls._deserialize_this(serialized)

        def get_typename(_serialized: dict[str, Any]) -> tuple[str, ...]:
            if 'type' in _serialized:
                typename = _serialized['type']
                return (typename,) + get_typename(_serialized[typename])
            return ()

        # (ex) KeyError: ('mention', 'user', 'person') -> ('mention', 'user')
        # TODO: fix this temporary hack!
        subclass = rich_text_span_registry[get_typename(serialized)[:2]]
        return subclass.deserialize(serialized)

    def __repr__(self):
        return self._repr_non_default_fields()


rich_text_span_registry: FinalClassDict[tuple[str, ...], type[RichTextSpan]] = FinalClassDict()


class RichText(list[RichTextSpan], DualSerializable):
    def __init__(self, spans: Iterable[RichTextSpan] = ()):
        super().__init__(spans)

    @property
    def plain_text(self) -> str:
        return ''.join(span.plain_text for span in self)

    @classmethod
    def from_plain_text(cls, plain_text: Optional[str]) -> Self:
        return cls([TextSpan(plain_text)]) if plain_text else cls()

    def serialize(self) -> Any:
        return serialize(self)

    @classmethod
    def _deserialize_this(cls, serialized: Any) -> Self:
        return cls(deserialize(list[RichTextSpan], serialized))


@dataclass
class TextSpan(RichTextSpan):
    content: str
    link: Optional[str] = None
    # ---
    annotations: Optional[Annotations] = None
    """
    Note: when updating block texts,
    * set `None` (the default value) to retain the current annotations.
    * set `Annotations()` to remove the annotations and make a plain text.
    """
    plain_text: Optional[str] = field(init=False, default=None, repr=False)
    href: Optional[str] = field(init=False, default=None, repr=False)

    def _serialize_main(self) -> dict[str, Any]:
        return {
            'type': 'text',
            'text': {
                'content': self.content,
                'link': {
                    'type': 'url',
                    'url': self.link
                } if self.link else None
            }
        }

    @classmethod
    def get_typename(cls) -> tuple[str, ...]:
        return 'text',

    @classmethod
    def _deserialize_main(cls, serialized: dict[str, Any]) -> Self:
        link_item = serialized['text']['link']
        link = link_item['url'] if link_item else None
        return cls(serialized['text']['content'], link)


@dataclass
class Equation(RichTextSpan):
    expression: str
    # ---
    annotations: Optional[Annotations] = None
    """
    Note: when updating block texts,
    * set `None` (the default value) to retain the current annotations.
    * set `Annotations()` to remove the annotations and make a plain text.
    """
    plain_text: Optional[str] = field(init=False, default=None, repr=False)
    href: Optional[str] = field(init=False, default=None, repr=False)

    def _serialize_main(self) -> dict[str, Any]:
        return {
            'type': 'equation',
            'expression': self.expression
        }

    @classmethod
    def get_typename(cls) -> tuple[str, ...]:
        return 'equation',

    @classmethod
    def _deserialize_main(cls, serialized: dict[str, Any]) -> Self:
        return cls(serialized['expression'])


@dataclass
class UserMention(RichTextSpan):
    user_id: UUID
    # ---
    annotations: Optional[Annotations] = None
    """
    Note: when updating block texts,
    * set `None` (the default value) to retain the current annotations.
    * set `Annotations()` to remove the annotations and make a plain text.
    """
    plain_text: Optional[str] = field(init=False, default=None, repr=False)
    href: Optional[str] = field(init=False, default=None, repr=False)

    def _serialize_main(self) -> dict[str, Any]:
        return {
            'type': 'mention',
            'mention': {
                'type': 'user',
                'user': {
                    'object': 'user',
                    'id': str(self.user_id)
                }
            }
        }

    @classmethod
    def get_typename(cls) -> tuple[str, ...]:
        return 'mention', 'user'

    @classmethod
    def _deserialize_main(cls, serialized: dict[str, Any]) -> Self:
        return cls(serialized['mention']['user']['id'])


@dataclass
class PageMention(RichTextSpan):
    page_id: UUID
    # ---
    annotations: Optional[Annotations] = None
    """
    Note: when updating block texts,
    * set `None` (the default value) to retain the current annotations.
    * set `Annotations()` to remove the annotations and make a plain text.
    """
    plain_text: Optional[str] = field(init=False, default=None, repr=False)
    href: Optional[str] = field(init=False, default=None, repr=False)

    def _serialize_main(self) -> dict[str, Any]:
        return {
            'type': 'mention',
            'mention': {
                'type': 'page',
                'page': str(self.page_id)
            }
        }

    @classmethod
    def get_typename(cls) -> tuple[str, ...]:
        return 'mention', 'page'

    @classmethod
    def _deserialize_main(cls, serialized: dict[str, Any]) -> Self:
        return cls(serialized['mention']['page'])


@dataclass
class DatabaseMention(RichTextSpan):
    database_id: UUID
    # ---
    annotations: Optional[Annotations] = None
    """
    Note: when updating block texts,
    * set `None` (the default value) to retain the current annotations.
    * set `Annotations()` to remove the annotations and make a plain text.
    """
    plain_text: Optional[str] = field(init=False, default=None, repr=False)
    href: Optional[str] = field(init=False, default=None, repr=False)

    def _serialize_main(self) -> dict[str, Any]:
        return {
            'type': 'mention',
            'mention': {
                'type': 'database',
                'database': str(self.database_id)
            }
        }

    @classmethod
    def get_typename(cls) -> tuple[str, ...]:
        return 'mention', 'database'

    @classmethod
    def _deserialize_main(cls, serialized: dict[str, Any]) -> Self:
        return cls(serialized['mention']['database'])


@dataclass
class DateMention(RichTextSpan):
    date: DateRange
    # ---
    annotations: Optional[Annotations] = None
    """
    Note: when updating block texts,
    * set `None` (the default value) to retain the current annotations.
    * set `Annotations()` to remove the annotations and make a plain text.
    """
    plain_text: Optional[str] = field(init=False, default=None, repr=False)
    href: Optional[str] = field(init=False, default=None, repr=False)

    def _serialize_main(self) -> dict[str, Any]:
        return {
            'type': 'mention',
            'mention': {
                'type': 'date',
                'date': self.date.serialize()
            }
        }

    @classmethod
    def get_typename(cls) -> tuple[str, ...]:
        return 'mention', 'date'

    @classmethod
    def _deserialize_main(cls, serialized: dict[str, Any]) -> Self:
        return cls(serialized['mention']['date'])


@dataclass
class TemplateDateMention(RichTextSpan):
    template_mention_date: Literal["today", "now"]
    # ---
    annotations: Optional[Annotations] = None
    """
    Note: when updating block texts,
    * set `None` (the default value) to retain the current annotations.
    * set `Annotations()` to remove the annotations and make a plain text.
    """
    plain_text: Optional[str] = field(init=False, default=None, repr=False)
    href: Optional[str] = field(init=False, default=None, repr=False)

    def _serialize_main(self) -> dict[str, Any]:
        return {
            'type': 'mention',
            'mention': {
                "type": "template_mention",
                "template_mention": {
                    "type": "template_mention_date",
                    "template_mention_date": self.template_mention_date
                }
            }
        }

    @classmethod
    def get_typename(cls) -> tuple[str, ...]:
        return 'mention', 'template_mention', 'template_mention_date'

    @classmethod
    def _deserialize_main(cls, serialized: dict[str, Any]) -> Self:
        return cls(serialized['mention']['database'])


@dataclass
class TemplateUserMention(RichTextSpan):
    template_mention_user = 'me'
    # ---
    annotations: Optional[Annotations] = None
    """
    Note: when updating block texts,
    * set `None` (the default value) to retain the current annotations.
    * set `Annotations()` to remove the annotations and make a plain text.
    """
    plain_text: Optional[str] = field(init=False, default=None, repr=False)
    href: Optional[str] = field(init=False, default=None, repr=False)

    def _serialize_main(self) -> dict[str, Any]:
        return {
            'type': 'mention',
            'mention': {
                "type": "template_mention",
                "template_mention": {
                    "type": "template_mention_user",
                    "template_mention_user": self.template_mention_user
                }
            }
        }

    @classmethod
    def get_typename(cls) -> tuple[str, ...]:
        return 'mention', 'template_mention', 'template_mention_user'

    @classmethod
    def _deserialize_main(cls, serialized: dict[str, Any]) -> Self:
        return cls()


@dataclass
class LinkPreviewMention(RichTextSpan):
    """https://developers.notion.com/reference/rich-text#link-preview-mentions"""
    url: str
    # ---
    annotations: Optional[Annotations] = None
    """
    Note: when updating block texts,
    * set `None` (the default value) to retain the current annotations.
    * set `Annotations()` to remove the annotations and make a plain text.
    """
    plain_text: Optional[str] = field(init=False, default=None, repr=False)
    href: Optional[str] = field(init=False, default=None, repr=False)

    def _serialize_main(self) -> dict[str, Any]:
        return {
            'type': 'mention',
            'mention': {
                'type': 'link_preview',
                'link_preview': {
                    'url': self.url
                }
            }
        }

    @classmethod
    def get_typename(cls) -> tuple[str, ...]:
        return 'mention', 'link_preview'

    @classmethod
    def _deserialize_main(cls, serialized: dict[str, Any]) -> Self:
        return cls(serialized['mention']['link_preview']['url'])
