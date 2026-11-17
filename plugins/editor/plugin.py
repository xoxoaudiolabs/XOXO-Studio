"""The sample editor, a default plug-in of the Studio's: the EDITOR tab and the touch editor (deskeditor.py), which a
pad's TRIM and "Edit as sample" open too; the web page's Editor answers while it's on. Off, none of them are
there. The edit itself (sampleui.SampleEditor, sampler.py's sums) is the Studio's: sampling a pad uses it."""
API = 1


def setup(studio):
    from deskeditor import EditorScreen
    from deskplugins import Tab

    class EditorTab(Tab):
        def screen(self):
            return self.ui.editor_screen()[1]

        def opened(self):
            """EDITOR: the file last edited, or the OPEN list the first time"""
            self.ui.tab = "EDITOR"
            self.screen().open_last()
            return True

        def edit(self, name, folder, pads=None):
            """a file into the editor (the sampler's TRIM: pads, its PADS tab, gets the pad's new sample back)"""
            self.screen().edit(name, folder, pads=pads)

        def draw(self, img, d, now):          # (the editor's screen is drawn while one's open: closed, HOME)
            self.home()

    studio.add_tab("EDITOR", EditorTab)
    studio.add_editor_screen(EditorScreen)
