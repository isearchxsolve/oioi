class Storyboard:
    def __init__(self):
        self.panels = {}
        self.links = {}

    def add_panel(self, description):
        panel_id = len(self.panels) + 1
        self.panels[panel_id] = {'description': description}
        return panel_id

    def link(self, panel1, panel2):
        if panel1 not in self.links:
            self.links[panel1] = []
        self.links[panel1].append(panel2)

    def edit_panel(self, panel_id, **kwargs):
        if panel_id in self.panels:
            self.panels[panel_id].update(kwargs)
            # Propagate to linked panels
            if panel_id in self.links:
                for linked_id in self.links[panel_id]:
                    if linked_id in self.panels:
                        self.panels[linked_id].update(kwargs)

    def get_panel(self, panel_id):
        return self.panels.get(panel_id, {})
