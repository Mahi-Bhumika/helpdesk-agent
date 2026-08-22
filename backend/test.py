from chunking import session, embed_chunks
print(session.get_inputs())  # should print input names like input_ids, attention_mask
print(embed_chunks(["This is a test sentence."])[0][:5])  # should print 5 floats