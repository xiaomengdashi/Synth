import test from 'node:test';
import assert from 'node:assert/strict';
import { remarkKnowledgeCitations } from './citations.ts';

test('citations skip code existing links and invalid numbers', () => {
  const tree: any = {type:'root',children:[{type:'paragraph',children:[{type:'text',value:'事实[1] 未知[9]'},{type:'inlineCode',value:'array[1]'},{type:'link',url:'/example',children:[{type:'text',value:'link[1]'}]}]},{type:'code',value:'code[1]'}]};
  remarkKnowledgeCitations({turnId:'turn-a',numbers:[1]})(tree);
  const children = tree.children[0].children;
  assert.equal(children[1].type, 'link');
  assert.equal(children[1].url, '#knowledge-source-turn-a-1');
  assert.equal(children[2].value, ' 未知[9]');
  assert.equal(children[3].value, 'array[1]');
  assert.equal(children[4].children[0].value, 'link[1]');
  assert.equal(tree.children[1].value, 'code[1]');
});
test('same citation number has a distinct anchor in each turn', () => {
  function url(id: string) {
    const tree: any = {type:'root', children:[{type:'paragraph',children:[{type:'text',value:'[1]'}]}]};
    remarkKnowledgeCitations({turnId:id,numbers:[1]})(tree);
    return tree.children[0].children[0].url;
  }
  assert.notEqual(url('one'), url('two'));
});
