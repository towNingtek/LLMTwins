from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from langchain.chains import SequentialChain

def create_sequential_chain(llm, template_profile, callback_handler, list_injection):
    # Insert the profile template to list_injection
    list_injection.insert(0, template_profile)

    # Create a chain for each injection from index 1
    for i, injection in enumerate(list_injection[1:], 1):
        injection = callback_handler.process_data(injection, i)
        # Create a prompt template
        prompt = None
        if (i == 1):
            prompt = PromptTemplate.from_template(template = injection)
        else:
            prompt = PromptTemplate(input_variables = [f"output_{i-1}"], template = injection)

        # Create a chain
        list_chain = []
        chain = LLMChain(llm = llm,
                         prompt = prompt,
                         callbacks = [callback_handler],
                         output_key = f"output_{i}",
                         verbose = True)

        list_chain.append(chain)

    # Create a sequential chain
    sequential_chain = SequentialChain(chains = list_chain, input_variables = ["question"], verbose = True)
    return sequential_chain