import { PageHome } from '~/components/scopes/page_home/page_home';
import { EXAMPLE_PROMPTS } from '~/configs/example_prompts';
import { shuffleArray } from '~/functions/shuffle_array';

/** How many prompts to show on the home page. */
const MAX_PROMPTS = 3;

const Page = () => {
  const randomPrompts = shuffleArray(EXAMPLE_PROMPTS).slice(0, MAX_PROMPTS);
  return <PageHome examplePrompts={randomPrompts} />;
};

export default Page;
