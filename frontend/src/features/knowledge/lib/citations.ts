type Node = {type: string; value?: string; url?: string; children?: Node[]};

export const sourceAnchorId = (turnId: string, number: number) => `knowledge-source-${turnId.replace(/[^a-zA-Z0-9_-]/g, '')}-${number}`;

export function remarkKnowledgeCitations(options: {turnId: string; numbers: number[]}) {
  const valid = new Set(options.numbers);
  function visit(node: Node) {
    if (['code','inlineCode','link','image','linkReference'].includes(node.type) || !node.children) return;
    node.children = node.children.flatMap(child => {
      if (child.type !== 'text') { visit(child); return [child]; }
      const value = child.value || '';
      const result: Node[] = [];
      let start = 0;
      for (const match of value.matchAll(/\[(\d+)\]/g)) {
        const number = Number(match[1]);
        if (!valid.has(number)) continue;
        if (match.index! > start) result.push({type:'text',value:value.slice(start, match.index)});
        result.push({type:'link',url:`#${sourceAnchorId(options.turnId, number)}`,children:[{type:'text',value:match[0]}]});
        start = match.index! + match[0].length;
      }
      if (start < value.length || !result.length) result.push({type:'text',value:value.slice(start)});
      return result;
    });
  }
  return (tree: Node) => visit(tree);
}
