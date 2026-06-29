import {
  ArrangeMenuSubmenu,
  ClipboardMenuGroup,
  DefaultContextMenu,
  ReorderMenuSubmenu,
  SelectAllMenuItem,
  type TLUiContextMenuProps,
  TldrawUiMenuGroup,
  useEditor,
  useValue,
} from 'tldraw';

/**
 * Right-click menu override. We rebuild tldraw's default content explicitly so
 * we control exactly which items appear — omit a child to remove that item.
 */
export const ContextMenu = (props: TLUiContextMenuProps) => {
  const editor = useEditor();

  const isSelectToolActive = useValue(
    'isSelectToolActive',
    () => editor.getCurrentToolId() === 'select',
    [editor],
  );

  if (isSelectToolActive) {
    return (
      <DefaultContextMenu {...props}>
        <TldrawUiMenuGroup id="modify">
          <ArrangeMenuSubmenu />
          <ReorderMenuSubmenu />
        </TldrawUiMenuGroup>
        <ClipboardMenuGroup />
        <TldrawUiMenuGroup id="select-all">
          <SelectAllMenuItem />
        </TldrawUiMenuGroup>
      </DefaultContextMenu>
    );
  }

  return <DefaultContextMenu {...props} />;
};
