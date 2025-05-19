from notion_df2.object.misc import Icon, File, ExternalFile


def test_icon():
    external_file_data = {"type": "external", "external": {"url": "self_url"}}
    assert isinstance(Icon.deserialize(external_file_data), ExternalFile)
    assert Icon.deserialize(external_file_data) == File.deserialize(external_file_data) == ExternalFile.deserialize(
        external_file_data)
