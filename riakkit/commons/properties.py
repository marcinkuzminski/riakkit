# This file is part of RiakKit.
#
# RiakKit is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# RiakKit is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with RiakKit.  If not, see <http://www.gnu.org/licenses/>.

import datetime
import time
from riakkit.commons.exceptions import RiakkitError
from riakkit.helpers import generateSalt, hashPassword, checkPassword
from uuid import uuid1

NONE_TYPE = type(None)
_valueOrList = lambda value: [] if value is None else value

class BaseProperty(object):
  """Base property type

  All property types are required to be extended from this class.

  Attributes:
    required: Enforce this property to be required. (Boolean)
    unique: Enforce this property to be unique. (Boolean)
    validators: A list of callables or 1 callable that validates any value
                given. The function should be callback(value), returning
                a boolean.
  """
  def __init__(self, required=False, unique=False, default=None,
               validators=None, forwardprocessors=None, backwardprocessors=None,
               standardprocessors=None):
    """Initializes the property field

    Args:
      required: A boolean that determines if this is required or not.
      unique: A boolean that determines if this is unique or not.
      validators: A list of callables of 1 callable that validates any value.
                  The function should be callback(value), returning a boolean.
      default: A custom default value or a function that generates a value.
      forwardprocessors: A list of callables or 1 callable that processes and
                         returns the data before convertToDb().
      backwardprocessors: A list of callables or 1 callables that processes the
                          data after getting it from the database and before
                          convertFromDb()

      standardprocessors: A list of callables or 1 callable that processes the
                          data when the data is being fed into the Document
                          object.

    """
    self.required = required
    self.unique = unique
    self.validators = _valueOrList(validators)
    self.default = default
    self.forwardprocessors = _valueOrList(forwardprocessors)
    self.backwardprocessors = _valueOrList(backwardprocessors)
    self.standardprocessors = _valueOrList(standardprocessors)
    self.name = None

  def _processValue(self, value, processors):
    if callable(processors):
      return processors(value)
    else:
      for processor in processors:
        value = processor(value)
    return value

  def hasValue(self, value):
    """Checks if a value exists in the db if the unique flag is turned on.

    Args:
      value: The value to check. No processing will be done here.

    Returns:
      True/False if it exist or not. None if the unique flag is not on.
    """
    if self.unique:
      return self.unique_bucket.get(value).exists()
    return None

  def convertToDb(self, value):
    """Converts the value from the access form a DB valid form

    In theory, the value should always be valid (as it has to undergo
    standardize before this is called).

    Must be able to handle None.

    Args:
      value: The value to be converted
    """
    return self._processValue(value, self.forwardprocessors)

  def convertFromDb(self, value):
    """Converts the value from the database back to an app friendly value (a
    value that standardize() will consider as valid).

    Note that the BaseProperty's convertFromDb will change the value from None
    (if that's how it was in the database) to the default value, if the default
    value is not None. This is done so that any attributes that's added after
    the object is saved that has a default value wouldn't be None.

    Must be able to handle None.

    Args:
      value: The value to be converted
    """
    default = self.defaultValue()
    if value is None and default is not None:
      value = default
    return self._processValue(value, self.backwardprocessors)

  def standardize(self, value):
    """Converts the value from any form (input form, db form) into a form that's
    friendly for the user to access via dot notation or dict-like notation in a
    Document object. (i.e. standard form) (example: string to unicode etc.)

    This method will be called on __setattr__.

    Must be able to handle None.

    Args:
      value: The value to be converted.

    Throws:
      TypeError: if type is not what's expected.

    """
    return self._processValue(value, self.standardprocessors)

  def validate(self, value):
    """The default validation function.

    This validation function goes through the validators and checks each one.
    Any subclass should do:

    return BaseProperty.validate(self, value) and your_result

    where your_result is your validation result.

    Args:
      value: The value to be validated

    Returns:
      True if validation pass, False otherwise.
    """

    if callable(self.validators):
      return self.validators(value)
    elif type(self.validators) in (tuple, list):
      for validator in self.validators:
        if not validator(value):
          return False

    return True

  def defaultValue(self):
    """The default value for this type.

    The default value is the value after being standardize()'d. Whenever an
    attribute is not present in the data when saved, this value will be
    substituted in.

    Returns:
      The default value for this type.
    """
    if callable(self.default):
      return self.default()

    return self.default


class DictProperty(BaseProperty):
  """Dictionary property, {}

  This property is somewhat special. After passing a dictionary to the field,
  you can use dot notation as well as dictionary notation.
  """

  class DotDict(dict):
    """A dictionary but allows dot notation to access the attributes
    (strings at least)
    """

    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

  # These will never have None, as the default value is always {}

  def standardize(self, value):
    value = BaseProperty.standardize(self, value)
    return DictProperty.DotDict(value)

  def convertFromDb(self, value):
    value = DictProperty.DotDict(value)
    return BaseProperty.convertFromDb(self, value)

  def validate(self, value):
    return BaseProperty.validate(self, value) and isinstance(value, (dict, NONE_TYPE))

  def defaultValue(self):
    """Default value for dictionary

    Returns:
      {}
    """
    return BaseProperty.defaultValue(self) or DictProperty.DotDict()

class ListProperty(BaseProperty):
  """List property, []"""
  def defaultValue(self):
    """Default value for list

    Returns:
      []
    """
    return BaseProperty.defaultValue(self) or []

class SetProperty(BaseProperty):
  """A set, using python's built-in set."""
  def standardize(self, value):
    value = BaseProperty.standardize(self, value)
    if value is None: return None
    return set(value)

  def convertToDb(self, value):
    value = BaseProperty.convertToDb(self, value)
    if value is None: return None
    return list(value)

  def convertFromDb(self, value):
    if value is not None:
      value = set(value)
    return BaseProperty.convertFromDb(self, value)

  def validate(self, value): # TODO: Combine this so it's not duplicate work?
    if value is None:
      checked = True
    try:
      set(value)
    except TypeError:
      checked = False
    else:
      checked = True

    return checked and BaseProperty.validate(self, value)

  def defaultValue(self):
    return BaseProperty.defaultValue(self) or set()

class StringProperty(BaseProperty):
  """String property. By default this converts strings to unicode."""
  def standardize(self, value):
    value = BaseProperty.standardize(self, value)
    if value is None: return None
    return unicode(value)

class IntegerProperty(BaseProperty):
  """Integer property."""
  def standardize(self, value):
    value = BaseProperty.standardize(self, value)
    if value is None: return None
    return int(value)

  def validate(self, value):
    if value is None:
      checked = True
    else:
      try:
        int(value)
      except ValueError:
        checked = False
      else:
        checked = True

    return checked and BaseProperty.validate(self, value)

class FloatProperty(BaseProperty):
  """Floating point property"""
  def standardize(self, value):
    value = BaseProperty.standardize(self, value)
    if value is None: return None
    return float(value)

  def validate(self, value):
    if value is None:
      checked = True
    else:
      try:
        float(value)
      except ValueError:
        checked = False
      else:
        checked = True

    return BaseProperty.validate(self, value) and checked

class BooleanProperty(BaseProperty):
  """Boolean property. Pretty self explanatory."""
  def standardize(self, value):
    value = BaseProperty.standardize(self, value)
    if value is None: return None
    return bool(value)

class EnumProperty(BaseProperty):
  """Not sure if enum is the best name, but this only allows some properties.

  This also only stores integers into database, making it efficient.
  The values you supply it initially will be the ones you get back (references
  will be kept if they are objects, so try to use basic types).
  """

  def __init__(self, possible_values, required=False, unique=False, default=None,
               validators=None, forwardprocessors=None, backwardprocessors=None):
    """Initialize the Enum Property.

    Args:
      possible_values: Possible values to be taken.

    Everything else is inheritted from BaseProperty.
    Note: Probably a bad idea using unique on this, but no one is preventing you
    """
    BaseProperty.__init__(self, required=required, unique=unique,
                                default=default, validators=validators,
                                forwardprocessors=forwardprocessors,
                                backwardprocessors=backwardprocessors)
    self._map_forward = {}
    self._map_backward = {}
    for i, v in enumerate(possible_values):
      self._map_forward[v] = i
      self._map_backward[i] = v

  def validate(self, value):
    return BaseProperty.validate(self, value) and (value is None or (value in self._map_forward))

  def convertToDb(self, value):
    value = BaseProperty.convertToDb(self, value)
    if value is None:
      return None

    return self._map_forward[value]

  def convertFromDb(self, value):
    if value is not None:
      value = self._map_backward[value]
    return BaseProperty.convertFromDb(self, value)

  def standardize(self, value):
    value = BaseProperty.standardize(self, value)
    if isinstance(value, int):
      return self._map_backward[value]
    elif isinstance(value, (str, NONE_TYPE)):
      return value

    raise TypeError("EnumProperty only accepts string and integer, not %s." % str(value))

class DateTimeProperty(BaseProperty):
  """The datetime property.

  Stores the time as a float in the database. Maps to the python object of
  datetime.datetime or the utc timestamp.

  Note that this is your timezone's time. Time is handled with your time only.

  TODO: utc only feature later.
  """

  def validate(self, value):
    check = False
    if isinstance(value, (long, int, float)): # timestamp
      try:
        value = datetime.datetime.fromtimestamp(value)
      except ValueError:
        check = False
      else:
        check = True
    elif isinstance(value, (datetime.datetime, NONE_TYPE)):
      check = True
    return BaseProperty.validate(self, value) and check

  def convertToDb(self, value):
    value = BaseProperty.convertToDb(self, value)
    if isinstance(value, (long, int, float, NONE_TYPE)):
      return value
    return time.mktime(value.timetuple())

  def convertFromDb(self, value):
    if value is not None:
      value = datetime.datetime.fromtimestamp(value)
    return BaseProperty.convertFromDb(self, value)

  def standardize(self, value):
    value = BaseProperty.standardize(self, value)
    if isinstance(value, (int, float, long)):
      return datetime.datetime.fromtimestamp(value)
    elif isinstance(value, (datetime.datetime, NONE_TYPE)):
      return value

    raise TypeError("DateTimeProperty only accepts integer, long, float, or datetime.datetime, not %s" % str(value))

  def defaultValue(self):
    """Returns the default specified or now."""
    if callable(self.default):
      return self.default()

    return self.default or datetime.datetime.fromtimestamp(time.time())


class DynamicProperty(BaseProperty):
  """Allows any type of property... Probably a bad idea, but sometimes useful.

  The implementation of this is exactly identical as BaseProperty. It doesn't
  do anything at all.. (except using your own validators).

  Warning: You may experience problems if your types doesn't play nice with
  Python json module...
  """

class ReferenceBaseProperty(BaseProperty):
  def __init__(self, reference_class, collection_name=None, required=False):
    """Initializes a Reference Property

    You can set it up so that riakkit automatically link back from
    the reference_class like GAE's ReferenceProperty. Except everything here
    is a list.

    Args:
      reference_class: The classes that should be added to this LinkedDocuments.
                       i.e. Documents have to be objects of that class to pass
                       validation. None if you wish to allow any Document class.
      collection_name: The collection name for the reference_class. Works the
                       same way as GAE's collection_name for their
                       ReferenceProperty. See the README file at the repository
                       for detailed tutorial.
    """
    BaseProperty.__init__(self, required=required)
    if not reference_class._clsType:
      raise TypeError("Reference property cannot be constructed with class '%s'" % reference_class.__name__)

    self.clstype = reference_class._clsType
    self.reference_class = reference_class
    self.collection_name = collection_name
    self.is_reference_back = False

  def _checkForReferenceClass(self, l):
    rc = self.reference_class

    if isinstance(l, list):
      for v in l:
        if not isinstance(v, (basestring, rc)):
          return False
      return True
    elif isinstance(l, dict):
      for k in l:
        if not isinstance(l[k], (basestring, rc)):
          return False
      return True
    else:
      return isinstance(l, (rc, basestring, NONE_TYPE))

  def attemptLoad(self, value): # TODO: Is this a hack?...
    if self.clstype == 1 or isinstance(value, (self.reference_class, NONE_TYPE)): # SimpleDocument
      return value
    else: # Document, EmDocument
      return self.reference_class.load(value, True)

  def attemptToDb(self, obj):
    if isinstance(obj, self.reference_class):
      return obj.key
    elif isinstance(obj, (basestring, NONE_TYPE)):
      return obj
    else:
      raise TypeError("WTF happened. %s.%s cannot have the type of %s" % (self.reference_class.__name__, self.name, str(type(obj))))

  def validate(self, value):
    check = self._checkForReferenceClass(value)
    return BaseProperty.validate(self, value) and check

  def deleteReference(self, doc, ref):
    return False

class ReferenceProperty(ReferenceBaseProperty):
  def convertToDb(self, value):
    value = BaseProperty.convertToDb(self, value)
    return self.attemptToDb(value)

  def deleteReference(self, doc, ref):
    if doc._data[self.name] is None:
      return False

    doc._data[self.name] = None
    return True

class MultiReferenceProperty(ReferenceBaseProperty):
  def convertToDb(self, value):
    value = BaseProperty.convertToDb(self, value)
    return [] if value is None else [self.attemptToDb(v) for v in value]

  def attemptLoad(self, value): # This is called when we do things like len(obj.multiprop). Should somehow erradicate the need for that.
    return [] if value is None else [ReferenceBaseProperty.attemptLoad(self, v) for v in value]

  def defaultValue(self):
    return []

  def deleteReference(self, doc, ref):
    currentList = doc._data.get(self.name)
    for i, r in enumerate(currentList): # TODO: Need a better search & destroy algorithm
      if isinstance(r, self.reference_class):
        key = r.key
      else:
        key = r

      if key == ref.key:
        currentList.pop(i) # This is a reference, which should modify the original list.
        return True

    return False

class DictReferenceProperty(ReferenceBaseProperty):
  """Dictionary based reference property.

  This doesn't allow collection_name.
  """

  def __init__(self, *args, **kwargs):
    ReferenceBaseProperty.__init__(self, *args, **kwargs)
    if self.collection_name:
      raise RiakkitError("collection_name not allowed with DictReferenceProperty!")


  def attemptLoad(self, value):
    new_values = {}
    for key in value:
      new_values[key] = ReferenceBaseProperty.attemptToLoad(self, value[key]) # key != value[key].key

    return new_values

  def convertToDb(self, value):
    value = BaseProperty.convertToDb(self, value)
    if value is None:
      return {}

    new_values = {}
    for key in value:
      new_values[key] = self.attemptToDb(value[key]) # key != value[key].key

    return new_values

  def convertFromDb(self, value):
    if value is None:
      value = {}
    return BaseProperty.convertFromDb(self, value)

  def defaultValue(self):
    return BaseProperty.defaultValue(self) or {}

  def deleteReference(self, doc, ref):
    current = doc._data.get(self.name)
    for k, r in current.iteritems():
      if r.key == ref.key:
        current.pop(k)
        return True
    return False

class EmDocumentProperty(BaseProperty):
  """The EmDocument property"""
  def __init__(self, emdocument_class, required=False, validators=None,
                     forwardprocessors=None, backwardprocessors=None):
    """Initializes a EmDocumentProperty class

    Args:
      emdocument_class: The EmDocument class to be used.
    """
    BaseProperty.__init__(self, required=required, validators=validators,
                                forwardprocessors=forwardprocessors,
                                backwardprocessors=backwardprocessors)
    self.emdocument_class = emdocument_class

  def validate(self, value):
    return BaseProperty.validate(self, value) and isinstance(value, (self.emdocument_class, NONE_TYPE, dict))

  def standardize(self, value):
    value = BaseProperty.standardize(self, value)
    if isinstance(value, self.emdocument_class):
      return value
    elif isinstance(value, dict):
      return self.emdocument_class(**value)
    elif value is None:
      return None
    else:
      raise TypeError("The type of the EmDocument must be dict or None.")

  def convertToDb(self, value):
    value = BaseProperty.convertToDb(self, value)
    return None if value is None else value.serialize()

  def convertFromDb(self, value):
    if value is not None:
      value = self.emdocument_class.constructObject(value)
    return BaseProperty.convertFromDb(self, value)

class EmDocumentsDictProperty(BaseProperty):
  """Property for a dictionary of EmDocuments.

  It would be like it's own key : EmDocuments. Example:
  {"yourkey" : EmDocument, "another_key" : EmDocument}

  This is for efficiency, as sometimes you want to grab a document given some
  property.

  However, no convinient dot access for this.. unless demanded.
  """
  class EmDocumentsDict(dict):
    """A special dict that converts values like EmDocumentProperty and
    EmDocumentsListProperty."""
    def __init__(self, emdocument_class, x=None, **kwargs):
      self.emdocument_class = emdocument_class
      dict.__init__(self)
      if x is not None:
        self.update(x)
      else:
        self.update(kwargs)

    def _standardize(self, x): # TODO: refactor and merge this with EmDocumentsListProperty
      if isinstance(x, (self.emdocument_class, NONE_TYPE)):
        value = x
      elif isinstance(x, dict):
        value = self.emdocument_class(**x)
      else:
        raise TypeError("The type of the EmDocument must be either dict or the class itself.")
      return value

    def __setitem__(self, key, value):
      dict.__setitem__(self, key, self._standardize(value))

    def setdefault(self, key, default=None):
      return dict.setdefault(self, key, self._standardize(default))

    def update(self, other=None, **kwargs):
      new_dict = {}
      if other is not None:
        if isinstance(other, dict):
          iteritems = other.iteritems()
        else:
          iteritems = other
      else:
        iteritems = kwargs
      for key, value in iteritems:
        new_dict[key] = self._standardize(value)
      dict.update(self, new_dict)

  def __init__(self, emdocument_class, required=False, validators=None,
                     forwardprocessors=None, backwardprocessors=None):
    """Initializes a EmDocumentsDictProperty class

    Args:
      emdocument_class: The EmDocument class to be used.
    """
    BaseProperty.__init__(self, required=required, validators=validators,
                                forwardprocessors=forwardprocessors,
                                backwardprocessors=backwardprocessors)
    self.emdocument_class = emdocument_class

  def standardize(self, value):
    value = BaseProperty.standardize(self, value)
    return EmDocumentsDictProperty.EmDocumentsDict(self.emdocument_class, value)

  def convertToDb(self, value):
    value = BaseProperty.convertToDb(self, value)
    if value is None:
      return None

    value = dict(value)
    for k, v in value.iteritems():
      value[k] = v.serialize()
    return value

  def convertFromDb(self, value):
    if value is not None:
      for k, v in value.iteritems():
        value[k] = self.emdocument_class.constructObject(v)
      value = EmDocumentsDictProperty.EmDocumentsDict(self.emdocument_class, value)
    return BaseProperty.convertFromDb(self, value)

  def defaultValue(self):
    return BaseProperty.defaultValue(self) or EmDocumentsDictProperty.EmDocumentsDict(self.emdocument_class)

class EmDocumentsListProperty(BaseProperty):
  """Property for a list of EmDocuments"""
  class EmDocumentsList(list):
    """A special list that's a child of the built in list. Upon append it
    converts values like EmDocumentProperty. All interfaces except init stays
    the same. __init__ takes in a mandatory emdocument_class
    """
    def __init__(self, emdocument_class, iterable=None):
      """Initializes the list.
      The iterable will be turned into EmDocuments as well.

      Args:
        emdocument_class: The class for the custom EmDocument
        iterable: The iterable of dictionary or the EmDocument objects
      """
      self.emdocument_class = emdocument_class
      new_list = self._standardizeList(_valueOrList(iterable))
      list.__init__(self, new_list)

    # Note that these standardize is not an actual property standardize.
    # They don't have the restriction of not being able to be called after
    # object reload.

    def _standardizeList(self, l):
      new_l = []
      for item in l:
        new_l.append(self._standardize(item))
      return new_l

    def _standardize(self, x):
      if isinstance(x, (self.emdocument_class, NONE_TYPE)):
        value = x
      elif isinstance(x, dict):
        value = self.emdocument_class(**x)
      else:
        raise TypeError("The type of the EmDocument must be either dict or the class itself.")
      return value

    def append(self, x):
      list.append(self, self._standardize(x))

    def insert(self, i, x):
      list.insert(self, i, self._standardize(x))

    def extend(self, x):
      list.extend(self, self._standardizeList(x))

    def __setitem__(self, name, value):
      value = self._standardize(value)
      list.__setitem__(self, name, value)

  def __init__(self, emdocument_class, required=False, validators=None,
                     forwardprocessors=None, backwardprocessors=None):
    """Initializes a EmDocumentsListProperty class

    Args:
      emdocument_class: The EmDocument class to be used.
    """
    BaseProperty.__init__(self, required=required, validators=validators,
                                forwardprocessors=forwardprocessors,
                                backwardprocessors=backwardprocessors)
    self.emdocument_class = emdocument_class

  def standardize(self, value):
    value = BaseProperty.standardize(self, value)
    return EmDocumentsListProperty.EmDocumentsList(self.emdocument_class, value)

  def convertToDb(self, value):
    value = BaseProperty.convertToDb(self, value)
    if value is None:
      return None

    value = list(value)
    for i, v in enumerate(value):
      value[i] = v.serialize()
    return value

  def convertFromDb(self, value):
    if value is not None:
      for i, v in enumerate(value):
        value[i] = self.emdocument_class.constructObject(v)
      value = EmDocumentsListProperty.EmDocumentsList(self.emdocument_class, value)
    return BaseProperty.convertFromDb(self, value)

  def defaultValue(self):
    return BaseProperty.defaultValue(self) or EmDocumentsListProperty.EmDocumentsList(self.emdocument_class)

## Value Added Pack Starts Here

class PasswordProperty(BaseProperty):
  def standardize(self, value):
    if not isinstance(value, basestring): # Feel like i'm doing too much of this. Isn't python all about ducttyping?
      raise TypeError("Password must be a string!")
    password = DictProperty.DotDict()
    salt = generateSalt()
    password.salt = salt
    password.hash = hashPassword(value, salt)
    return password

  def convertFromDb(self, value):
    return DictProperty.DotDict(value)
