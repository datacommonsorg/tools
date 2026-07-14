import { PageHome } from '~/components/scopes/page_home/page_home';
import { EXAMPLE_PROMPTS } from '~/configs/example_prompts';
import { shuffleArray } from '~/functions/shuffle_array';

const Page = () => {
  const prompts = shuffleArray(EXAMPLE_PROMPTS).slice(0, 4);
  return <PageHome examplePrompts={prompts} />;
};

export default Page;
