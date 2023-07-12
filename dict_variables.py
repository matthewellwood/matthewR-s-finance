# Python3 code to demonstrate working of
# Extracting key-value of dictionary in variables
# Using iter() + next()

# Initialize dictionary
test_dict = {'symbol': 'amzn'}

# printing original dictionary
print("The original dictionary : " +  str(test_dict))

# Using iter() + next()
# Extracting key-value of dictionary in variables
key, val = next(iter(test_dict.items()))

# printing result
print("The 1st key of dictionary is : " + str(key))
print("The 1st value of dictionary is : " + str(val))