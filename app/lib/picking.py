import numpy as np

tmp = np.load('/home/uas/opencv/datasets/cland/cland_day3_flight1/flight1_cland1_C_straight/numpy_arrays/EKF1.npy')
print(tmp.dtype.fields)
print(tmp['Roll'])
from bokeh.models import TapTool, CustomJS, ColumnDataSource, LegendItem, Legend
from bokeh.plotting import output_file, show, figure

from bokeh.models import LinearAxis, Range1d, BoxAnnotation, HoverTool, Span
from bokeh.plotting import figure, show, output_file

# The data is setup to have very different scales in x and y, to verify
# that picking happens in pixels. Different widths are used to test that
# you can click anywhere on the visible line.
#
# Note that the get_view() function used here is not documented and
# might change in future versions of Bokeh.
t = tmp['timestamp']

code = """


d0 = cb_obj.selected["0d"];
console.log(d0)


if (d0.glyph) {
    var color = d0.get_view().visuals.line.line_color.value();
    var data = source.data;
    data['text'] = ['Selected the ' + color + ' line'];
    source.trigger('change');
}
"""

# use a source to easily update the text of the text-glyph
#source = ColumnDataSource(data=dict(text=['no line selected']))




TOOLS = ['box_zoom,pan,crosshair,reset,wheel_zoom,save,redo,undo']
p = figure(plot_width=1300,plot_height = 900, sizing_mode='scale_both',tools=TOOLS)
b1 = BoxAnnotation(left=2.961807e10, fill_alpha=0.1, fill_color='red',render_mode='css')
p.add_layout(b1) #right = 


p.extra_y_ranges['foo'] = Range1d(0, 50)
p.extra_y_ranges['barr'] = Range1d(0, 100)

y = tmp['Roll']
y2 = tmp['Pitch']
y3 = tmp['Yaw']

l1 = p.line(t, y, color='red', line_width=1, legend="Record")
l2 = p.line(t, y2, color='green', line_width=1, y_range_name="foo")
l3 = p.line(t, y3, color='blue',  line_width=1, y_range_name="barr")

#p.scatter(t, y, marker='cross', size=15, line_color="navy", fill_color="orange", alpha=0.5)
#p.text(0, -100, source=source)

p.add_layout(LinearAxis(y_range_name="foo"), 'left')
p.add_layout(LinearAxis(y_range_name="barr"), 'left')

p.xaxis.axis_label = "Time"
p.yaxis.axis_label = " "

#support for mode colours

legend = Legend(items=[
    LegendItem(label="sin(x)", renderers=[]),
    LegendItem(label="2*sin(x)", renderers=[]),
    LegendItem(label="3*sin(x)", renderers=[])
])



source = ColumnDataSource({'x0': [2.961807e10]})

vline_code = """
var x_idx = cb_data.index['0d'].indices[0]
console.log(x_idx)
vline.location = cb_data.geometry.x
""" 

vline = Span(location=source.data['x0'][0], dimension='height', line_color='red', line_width=1,render_mode='css')
p.renderers.extend([vline])

callback1 = CustomJS(args={'vline': vline}, code=vline_code)
hover2 = HoverTool(callback=callback1)
hover2.tooltips = [
    ("x,y", "(@x, @y)")
#("color", "$color[swatch]")
]
hover2.point_policy='snap_to_data'
hover2.line_policy='nearest'#'prev'
hover2.mode = 'vline'

p.add_tools(hover2)

output_file("line_select.html", title="line_select.py example")

show(p)
