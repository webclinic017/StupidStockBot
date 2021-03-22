from plotly.subplots import make_subplots
import plotly.graph_objects as go
import dash
import dash_core_components as dcc
import dash_html_components as html


def plot_stuff(dataLong, dataShort, longTicker, shortTicker):
    allPlots = [dataLong, dataShort]

    fig = make_subplots(rows=len(allPlots), cols=1)

    for i, tickerPlot in enumerate(allPlots):
        fig.add_trace(go.Ohlc(x=tickerPlot.index,
                              open=tickerPlot.Open,
                              high=tickerPlot.High,
                              low=tickerPlot.Low,
                              close=tickerPlot.Close), i + 1, 1)
        fig.update_xaxes(rangeslider={'visible': False}, type='category', row=i + 1, col=1)

    fig.update(layout_xaxis_rangeslider_visible=False)
    fig.update_layout(height=800, width=1000,
                      title_text=f'TOP: {longTicker} \nBottom: {shortTicker}',
                      showlegend=False)

    app = dash.Dash()
    app.layout = html.Div([
        dcc.Graph(figure=fig)
    ])

    app.run_server(debug=True, use_reloader=False)
    return
